"""Service layer orchestrating MCP server discovery, static tool extraction, and version diffing."""

from typing import Any, Dict, List, Optional, Set
from app.schemas.mcp import (
    CompareMCPToolsResponse,
    DiscoverMCPResponse,
    DiscoveredServer,
    ExtractedTool,
    MCPServerDiscovery,
    ServerComparison,
    ToolComparisonSummary,
    ToolDifference,
)
from app.services.github_service import (
    GitHubError,
    GitHubRateLimitError,
    GitHubService,
    parse_github_repository_url,
)
from app.services.mcp_extractor import MCPExtractor, is_test_file


class MCPService:
    """Service orchestrating static discovery of MCP servers and comparing tool inventories between releases."""

    def __init__(self, github_service: GitHubService):
        self.github = github_service

    async def discover_tools_for_ref(
        self, repository_url: str, ref: str
    ) -> DiscoverMCPResponse:
        """Resolve a git ref, fetch repository manifest and source files safely, and perform static MCP discovery."""
        owner, repo, canonical_url = parse_github_repository_url(repository_url)
        commit = await self.github.resolve_ref(owner, repo, ref, ref_label="target")
        commit_sha = commit.sha

        discovery = await self._run_static_discovery(owner, repo, commit_sha)

        return DiscoverMCPResponse(
            status="success",
            repository_url=canonical_url,
            ref=ref,
            commit_sha=commit_sha,
            discovery=discovery,
        )

    async def compare_tools_between_refs(
        self, repository_url: str, baseline_ref: str, candidate_ref: str
    ) -> CompareMCPToolsResponse:
        """Resolve baseline and candidate refs, extract tools for both versions, and compute deterministic tool diffs."""
        owner, repo, canonical_url = parse_github_repository_url(repository_url)

        # Resolve both refs to exact immutable SHAs with specific baseline/candidate labels
        baseline_commit = await self.github.resolve_ref(owner, repo, baseline_ref, ref_label="baseline")
        candidate_commit = await self.github.resolve_ref(owner, repo, candidate_ref, ref_label="candidate")

        baseline_sha = baseline_commit.sha
        candidate_sha = candidate_commit.sha

        # If identical commit SHAs, run discovery once to avoid redundant network/AST operations
        if baseline_sha == candidate_sha:
            discovery = await self._run_static_discovery(owner, repo, baseline_sha)
            differences = [
                ToolDifference(
                    tool_name=tool.name,
                    server_id=tool.server_name,
                    change_type="unchanged",
                    baseline_tool=tool,
                    candidate_tool=tool,
                    changes_detected=[],
                )
                for tool in discovery.extracted_tools
            ]
            is_complete = discovery.extraction_status == "COMPLETE"
            summary = ToolComparisonSummary(
                total_baseline_tools=len(discovery.extracted_tools),
                total_candidate_tools=len(discovery.extracted_tools),
                added_count=0,
                removed_count=0,
                modified_count=0,
                unchanged_count=len(discovery.extracted_tools),
                is_complete=is_complete,
            )
            server_comparisons = [
                ServerComparison(
                    server_id=s.server_id,
                    server_name=s.name,
                    baseline_entrypoint=s.entrypoint,
                    candidate_entrypoint=s.entrypoint,
                    status="matched",
                    summary=ToolComparisonSummary(
                        total_baseline_tools=len(s.tools),
                        total_candidate_tools=len(s.tools),
                        added_count=0,
                        removed_count=0,
                        modified_count=0,
                        unchanged_count=len(s.tools),
                        is_complete=is_complete,
                    ),
                    differences=[
                        ToolDifference(
                            tool_name=tool.name,
                            server_id=s.server_id,
                            change_type="unchanged",
                            baseline_tool=tool,
                            candidate_tool=tool,
                            changes_detected=[],
                        )
                        for tool in s.tools
                    ],
                )
                for s in discovery.servers
            ]
            return CompareMCPToolsResponse(
                status="success",
                repository_url=canonical_url,
                baseline_ref=baseline_ref,
                baseline_sha=baseline_sha,
                candidate_ref=candidate_ref,
                candidate_sha=candidate_sha,
                baseline_discovery=discovery,
                candidate_discovery=discovery,
                summary=summary,
                differences=differences,
                server_comparisons=server_comparisons,
            )

        # Discover tools in baseline and candidate independently
        baseline_discovery = await self._run_static_discovery(owner, repo, baseline_sha)
        candidate_discovery = await self._run_static_discovery(owner, repo, candidate_sha)

        server_comparisons = self.compare_servers(
            baseline_discovery.servers, candidate_discovery.servers
        )

        # Derive repository-wide differences directly from server_comparisons
        all_differences: List[ToolDifference] = []
        for sc in server_comparisons:
            all_differences.extend(sc.differences)

        all_differences.sort(key=lambda d: (d.tool_name, d.server_id or ""))

        is_complete = (
            baseline_discovery.extraction_status == "COMPLETE"
            and candidate_discovery.extraction_status == "COMPLETE"
        )

        summary = ToolComparisonSummary(
            total_baseline_tools=sum(sc.summary.total_baseline_tools for sc in server_comparisons),
            total_candidate_tools=sum(sc.summary.total_candidate_tools for sc in server_comparisons),
            added_count=sum(sc.summary.added_count for sc in server_comparisons),
            removed_count=sum(sc.summary.removed_count for sc in server_comparisons),
            modified_count=sum(sc.summary.modified_count for sc in server_comparisons),
            unchanged_count=sum(sc.summary.unchanged_count for sc in server_comparisons),
            is_complete=is_complete,
        )

        return CompareMCPToolsResponse(
            status="success",
            repository_url=canonical_url,
            baseline_ref=baseline_ref,
            baseline_sha=baseline_sha,
            candidate_ref=candidate_ref,
            candidate_sha=candidate_sha,
            baseline_discovery=baseline_discovery,
            candidate_discovery=candidate_discovery,
            summary=summary,
            differences=all_differences,
            server_comparisons=server_comparisons,
        )

    async def _run_static_discovery(
        self, owner: str, repo: str, commit_sha: str
    ) -> MCPServerDiscovery:
        """Fetch git tree and inspect relevant source files without code execution."""
        extractor = MCPExtractor(owner, repo, commit_sha)

        try:
            tree_entries = await self.github.get_commit_tree(owner, repo, commit_sha)
        except GitHubRateLimitError as exc:
            extractor.extraction_status = "FAILED"
            extractor.warnings.append(f"Discovery FAILED: GitHub API rate limit reached ({str(exc)}).")
            return extractor.generate_discovery_report()
        except GitHubError as exc:
            extractor.extraction_status = "FAILED"
            extractor.warnings.append(f"Discovery FAILED: Could not retrieve git tree ({exc.message}).")
            return extractor.generate_discovery_report()

        manifest_files: List[str] = []
        python_files: List[str] = []

        for entry in tree_entries:
            path = entry.get("path", "")
            lower_path = path.lower()
            if entry.get("type") != "blob":
                continue

            # Skip tests, hidden directories, vendor, docs, and build caches
            if is_test_file(path) or any(
                part.startswith(".")
                or part in ("node_modules", "vendor", "dist", "build", ".venv", "venv", "site-packages", "docs")
                for part in path.split("/")
            ):
                continue

            if lower_path.endswith("pyproject.toml") or lower_path.endswith("requirements.txt") or lower_path.endswith("package.json"):
                manifest_files.append(path)
            elif lower_path.endswith(".py"):
                python_files.append(path)

        # 1. Process dependency manifests
        for m_path in manifest_files:
            try:
                content = await self.github.get_file_content(owner, repo, m_path, commit_sha)
                if content:
                    extractor.inspect_dependencies(m_path, content)
            except GitHubRateLimitError as exc:
                extractor.extraction_status = "FAILED"
                extractor.warnings.append(f"Extraction halted: GitHub rate limit exceeded while reading '{m_path}'.")
                return extractor.generate_discovery_report()
            except Exception as exc:
                extractor.extraction_status = "PARTIAL"
                extractor.warnings.append(f"Could not read manifest '{m_path}': {str(exc)}")

        # 2. Select priority Python files for inspection (max 40 files)
        def file_priority(p: str) -> int:
            base = p.split("/")[-1].lower()
            if base in ("server.py", "main.py", "app.py", "mcp_server.py"):
                return 0
            if "server" in base or "mcp" in base:
                return 1
            if p.count("/") <= 1:
                return 2
            return 3

        sorted_py_files = sorted(python_files, key=file_priority)
        selected_py_files = sorted_py_files[:40]

        if len(sorted_py_files) > 40:
            skipped_count = len(sorted_py_files) - 40
            extractor.extraction_status = "PARTIAL"
            extractor.warnings.append(
                f"Repository contains {len(sorted_py_files)} Python source files. Inspected top 40 files; {skipped_count} files were omitted due to inspection limits."
            )

        # 3. Analyze AST of selected Python source files
        for py_path in selected_py_files:
            try:
                content = await self.github.get_file_content(owner, repo, py_path, commit_sha)
                if content:
                    extractor.analyze_python_source(py_path, content)
            except GitHubRateLimitError as exc:
                extractor.extraction_status = "FAILED"
                extractor.warnings.append(f"Extraction halted: GitHub rate limit exceeded while reading '{py_path}'.")
                return extractor.generate_discovery_report()
            except Exception as exc:
                extractor.extraction_status = "PARTIAL"
                extractor.warnings.append(f"Could not read source '{py_path}': {str(exc)}")

        return extractor.generate_discovery_report()

    @staticmethod
    def compare_servers(
        baseline_servers: List[DiscoveredServer],
        candidate_servers: List[DiscoveredServer],
    ) -> List[ServerComparison]:
        """Compare tools grouped by their respective server implementations.
        
        Matches corresponding server implementations by exact entrypoint or unique name,
        and explicitly reports unmatched or ambiguous identities.
        """
        server_comparisons: List[ServerComparison] = []

        cand_by_ep: Dict[str, List[DiscoveredServer]] = {}
        for s in candidate_servers:
            cand_by_ep.setdefault(s.entrypoint, []).append(s)

        base_by_ep: Dict[str, List[DiscoveredServer]] = {}
        for s in baseline_servers:
            base_by_ep.setdefault(s.entrypoint, []).append(s)

        matched_base_ids: Set[str] = set()
        matched_cand_ids: Set[str] = set()

        # Step 1: Match servers sharing the exact same entrypoint path
        common_eps = set(base_by_ep.keys()) & set(cand_by_ep.keys())
        for ep in sorted(common_eps):
            b_list = base_by_ep[ep]
            c_list = cand_by_ep[ep]
            if len(b_list) == 1 and len(c_list) == 1:
                b_srv = b_list[0]
                c_srv = c_list[0]
                diffs, summary = MCPService.compute_tool_diff(b_srv.tools, c_srv.tools)
                server_comparisons.append(
                    ServerComparison(
                        server_id=c_srv.server_id,
                        server_name=c_srv.name,
                        baseline_entrypoint=b_srv.entrypoint,
                        candidate_entrypoint=c_srv.entrypoint,
                        status="matched",
                        summary=summary,
                        differences=diffs,
                    )
                )
                matched_base_ids.add(b_srv.server_id)
                matched_cand_ids.add(c_srv.server_id)

        # Step 2: For remaining unmatched servers, attempt match by unique server name
        unmatched_base = [s for s in baseline_servers if s.server_id not in matched_base_ids]
        unmatched_cand = [s for s in candidate_servers if s.server_id not in matched_cand_ids]

        base_by_name: Dict[str, List[DiscoveredServer]] = {}
        for s in unmatched_base:
            base_by_name.setdefault(s.name, []).append(s)

        cand_by_name: Dict[str, List[DiscoveredServer]] = {}
        for s in unmatched_cand:
            cand_by_name.setdefault(s.name, []).append(s)

        all_unmatched_names = set(base_by_name.keys()) | set(cand_by_name.keys())
        for name in sorted(all_unmatched_names):
            b_list = base_by_name.get(name, [])
            c_list = cand_by_name.get(name, [])

            # 2a. Exactly 1 in baseline and 1 in candidate -> unambiguous match
            if len(b_list) == 1 and len(c_list) == 1:
                b_srv = b_list[0]
                c_srv = c_list[0]
                diffs, summary = MCPService.compute_tool_diff(b_srv.tools, c_srv.tools)
                server_comparisons.append(
                    ServerComparison(
                        server_id=c_srv.server_id,
                        server_name=name,
                        baseline_entrypoint=b_srv.entrypoint,
                        candidate_entrypoint=c_srv.entrypoint,
                        status="matched",
                        summary=summary,
                        differences=diffs,
                    )
                )
                matched_base_ids.add(b_srv.server_id)
                matched_cand_ids.add(c_srv.server_id)

            # 2b. Multiple servers share the same name across different entrypoints -> AMBIGUOUS!
            elif (len(b_list) > 1 and len(c_list) >= 1) or (len(c_list) > 1 and len(b_list) >= 1):
                # Report ambiguous server identities explicitly rather than silently guessing pairings
                for s in c_list:
                    diffs, summary = MCPService.compute_tool_diff([], s.tools)
                    server_comparisons.append(
                        ServerComparison(
                            server_id=s.server_id,
                            server_name=s.name,
                            baseline_entrypoint=None,
                            candidate_entrypoint=s.entrypoint,
                            status="ambiguous",
                            summary=summary,
                            differences=diffs,
                        )
                    )
                    matched_cand_ids.add(s.server_id)

                for s in b_list:
                    diffs, summary = MCPService.compute_tool_diff(s.tools, [])
                    server_comparisons.append(
                        ServerComparison(
                            server_id=s.server_id,
                            server_name=s.name,
                            baseline_entrypoint=s.entrypoint,
                            candidate_entrypoint=None,
                            status="ambiguous",
                            summary=summary,
                            differences=diffs,
                        )
                    )
                    matched_base_ids.add(s.server_id)

        # Step 3: Remaining unmatched candidate servers -> added
        for s in candidate_servers:
            if s.server_id not in matched_cand_ids:
                diffs, summary = MCPService.compute_tool_diff([], s.tools)
                server_comparisons.append(
                    ServerComparison(
                        server_id=s.server_id,
                        server_name=s.name,
                        baseline_entrypoint=None,
                        candidate_entrypoint=s.entrypoint,
                        status="added",
                        summary=summary,
                        differences=diffs,
                    )
                )
                matched_cand_ids.add(s.server_id)

        # Step 4: Remaining unmatched baseline servers -> removed
        for s in baseline_servers:
            if s.server_id not in matched_base_ids:
                diffs, summary = MCPService.compute_tool_diff(s.tools, [])
                server_comparisons.append(
                    ServerComparison(
                        server_id=s.server_id,
                        server_name=s.name,
                        baseline_entrypoint=s.entrypoint,
                        candidate_entrypoint=None,
                        status="removed",
                        summary=summary,
                        differences=diffs,
                    )
                )
                matched_base_ids.add(s.server_id)

        server_comparisons.sort(key=lambda sc: (sc.server_name, sc.server_id))
        return server_comparisons

    @staticmethod
    def compute_tool_diff(
        baseline_tools: List[ExtractedTool],
        candidate_tools: List[ExtractedTool],
    ) -> tuple[List[ToolDifference], ToolComparisonSummary]:
        """Compute deterministic, order-independent differences between two tool inventories.
        
        Avoids collisions when distinct servers define tools with the same name.
        """
        # If multiple servers exist within the tool lists, scope key by server_name
        base_servers = {t.server_name for t in baseline_tools if t.server_name}
        cand_servers = {t.server_name for t in candidate_tools if t.server_name}
        has_multi_server = len(base_servers) > 1 or len(cand_servers) > 1

        def tool_key(t: ExtractedTool) -> str:
            if has_multi_server and t.server_name:
                return f"{t.server_name}:{t.name}"
            return t.name

        base_map: Dict[str, ExtractedTool] = {tool_key(t): t for t in baseline_tools}
        cand_map: Dict[str, ExtractedTool] = {tool_key(t): t for t in candidate_tools}

        all_keys = sorted(list(set(base_map.keys()) | set(cand_map.keys())))

        differences: List[ToolDifference] = []
        added_count = 0
        removed_count = 0
        modified_count = 0
        unchanged_count = 0

        for key in all_keys:
            in_base = key in base_map
            in_cand = key in cand_map

            if in_cand and not in_base:
                cand_tool = cand_map[key]
                differences.append(
                    ToolDifference(
                        tool_name=cand_tool.name,
                        server_id=cand_tool.server_name,
                        change_type="added",
                        baseline_tool=None,
                        candidate_tool=cand_tool,
                        changes_detected=["Tool introduced in candidate version"],
                    )
                )
                added_count += 1

            elif in_base and not in_cand:
                base_tool = base_map[key]
                differences.append(
                    ToolDifference(
                        tool_name=base_tool.name,
                        server_id=base_tool.server_name,
                        change_type="removed",
                        baseline_tool=base_tool,
                        candidate_tool=None,
                        changes_detected=["Tool removed from candidate version"],
                    )
                )
                removed_count += 1

            else:
                base_tool = base_map[key]
                cand_tool = cand_map[key]

                changes_detected: List[str] = []

                # Description comparison
                base_desc = (base_tool.description or "").strip()
                cand_desc = (cand_tool.description or "").strip()
                desc_changed = base_desc != cand_desc
                if desc_changed:
                    changes_detected.append("Description was updated")

                # Schema comparison via precomputed canonical hash
                schema_changed = base_tool.schema_hash != cand_tool.schema_hash
                if schema_changed:
                    base_props = base_tool.input_schema.get("properties", {})
                    cand_props = cand_tool.input_schema.get("properties", {})

                    added_props = set(cand_props.keys()) - set(base_props.keys())
                    removed_props = set(base_props.keys()) - set(cand_props.keys())

                    for p in sorted(added_props):
                        changes_detected.append(f"Added input parameter '{p}'")
                    for p in sorted(removed_props):
                        changes_detected.append(f"Removed input parameter '{p}'")

                    for p in sorted(set(base_props.keys()) & set(cand_props.keys())):
                        b_def = base_props.get(p, {})
                        c_def = cand_props.get(p, {})
                        if isinstance(b_def, dict) and isinstance(c_def, dict):
                            if b_def.get("type") != c_def.get("type"):
                                changes_detected.append(
                                    f"Parameter '{p}' type changed from {b_def.get('type')} to {c_def.get('type')}"
                                )
                            if b_def.get("enum") != c_def.get("enum"):
                                changes_detected.append(f"Parameter '{p}' enum constraints changed")

                    base_req = set(base_tool.input_schema.get("required", []))
                    cand_req = set(cand_tool.input_schema.get("required", []))
                    added_req = cand_req - base_req
                    removed_req = base_req - cand_req

                    for r in sorted(added_req):
                        changes_detected.append(f"Parameter '{r}' is now required")
                    for r in sorted(removed_req):
                        changes_detected.append(f"Parameter '{r}' is no longer required")

                    if not changes_detected:
                        changes_detected.append("Input schema structure was modified")

                if desc_changed and schema_changed:
                    change_type = "modified_both"
                    modified_count += 1
                elif schema_changed:
                    change_type = "modified_schema"
                    modified_count += 1
                elif desc_changed:
                    change_type = "modified_description"
                    modified_count += 1
                else:
                    change_type = "unchanged"
                    unchanged_count += 1

                differences.append(
                    ToolDifference(
                        tool_name=cand_tool.name,
                        server_id=cand_tool.server_name or base_tool.server_name,
                        change_type=change_type,
                        baseline_tool=base_tool,
                        candidate_tool=cand_tool,
                        changes_detected=changes_detected,
                    )
                )

        summary = ToolComparisonSummary(
            total_baseline_tools=len(baseline_tools),
            total_candidate_tools=len(candidate_tools),
            added_count=added_count,
            removed_count=removed_count,
            modified_count=modified_count,
            unchanged_count=unchanged_count,
        )

        return differences, summary
