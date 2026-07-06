# Graph Report - .  (2026-07-06)

## Corpus Check
- 144 files · ~146,083 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 731 nodes · 1290 edges · 59 communities (49 shown, 10 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 92 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `abbd04ad`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]

## God Nodes (most connected - your core abstractions)
1. `AuthError` - 43 edges
2. `make_request()` - 24 edges
3. `authenticate()` - 16 edges
4. `execute()` - 13 edges
5. `PDF` - 13 edges
6. `HttpRequest` - 12 edges
7. `HttpResponse` - 12 edges
8. `SaveRequest` - 11 edges
9. `build_body()` - 11 edges
10. `make_request()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `HttpRequest` --uses--> `AuthError`  [INFERRED]
  03-edit-master-table/master-tables/02backend/modules/gl_group/list_handler.py → 03-edit-master-table/master-tables/02backend/auth.py
- `HttpResponse` --uses--> `AuthError`  [INFERRED]
  03-edit-master-table/master-tables/02backend/modules/gl_group/list_handler.py → 03-edit-master-table/master-tables/02backend/auth.py
- `HttpRequest` --uses--> `AuthError`  [INFERRED]
  03-edit-master-table/master-tables/02backend/modules/gl_group/reference_handler.py → 03-edit-master-table/master-tables/02backend/auth.py
- `HttpResponse` --uses--> `AuthError`  [INFERRED]
  03-edit-master-table/master-tables/02backend/modules/gl_group/reference_handler.py → 03-edit-master-table/master-tables/02backend/auth.py
- `HttpRequest` --uses--> `AuthError`  [INFERRED]
  03-edit-master-table/master-tables/02backend/modules/hide_document/list_handler.py → 03-edit-master-table/master-tables/02backend/auth.py

## Import Cycles
- None detected.

## Communities (59 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (39): _conn_str(), execute(), exists(), fetchall(), fetchall_lakehouse(), fetchone(), find_group_id_by_name(), get_conn() (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (25): make_request(), Unit tests for Orgcode & Cost Center Mapping handlers (module 0007).  All extern, Edge case: orgcode_name is '' (COALESCE) not None — silent NULL would         ca, Happy path: new pair → INSERT → 200 {status: success}., Duplicate: exists() returns True → 409 with DUPLICATE_KEY code., TOCTOU race: exists()=False but INSERT raises IntegrityError.          BUG REPOR, Invalid payload: missing orgcode → 400., Invalid payload: missing cost_center → 400. (+17 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (26): closeConfirm(), deleteCC(), deleteOrg(), editCC(), editOrg(), escapeHtml(), executeConfirmedDelete(), flashWarning() (+18 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (33): annotate(), body_para(), build_annotated_images(), build_body(), bullet(), cell_para(), content_types_xml(), document_rels_xml() (+25 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (22): askDelete(), closeConfirm(), createNewGroup(), editRecord(), escapeHtml(), executeConfirmedDelete(), glGroupDims, masterData (+14 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (29): annotate(), body_para(), build_annotated_images(), build_body(), bullet(), cell_para(), content_types_xml(), document_rels_xml() (+21 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (29): annotate(), body_para(), build_annotated_images(), build_body(), bullet(), cell_para(), content_types_xml(), document_rels_xml() (+21 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (29): annotate(), body_para(), build_annotated_images(), build_body(), bullet(), cell_para(), content_types_xml(), document_rels_xml() (+21 more)

### Community 8 - "Community 8"
Cohesion: 0.16
Nodes (29): annotate(), body_para(), build_annotated_images(), build_body(), bullet(), cell_para(), content_types_xml(), document_rels_xml() (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.18
Nodes (24): annotate(), body_para(), build_body(), bullet(), capture(), cell_para(), _circle(), content_types_xml() (+16 more)

### Community 10 - "Community 10"
Cohesion: 0.19
Nodes (25): annotate(), body_para(), build_body(), bullet(), capture(), cell_para(), _circle(), content_types_xml() (+17 more)

### Community 11 - "Community 11"
Cohesion: 0.19
Nodes (25): annotate(), body_para(), build_body(), bullet(), capture(), cell_para(), _circle(), content_types_xml() (+17 more)

### Community 12 - "Community 12"
Cohesion: 0.12
Nodes (14): DataLakeServiceClient, get_fs_client(), main(), AccessToken, Path, Ingest SAP flat files from local path → Fabric Lakehouse Files/00landing  Source, _StaticTokenCredential, upload_file() (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.17
Nodes (19): _border(), build_excel(), _center(), download_from_sharepoint(), _fill(), _font(), _get_token(), _left() (+11 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (14): BaseModel, GlGroupMappingBase, ListResponseItem, Pydantic models for GL Group Master JSON payloads.  Validation rules sourced fro, Core fields of a GL Group mapping row., One row in GET /list response., DeleteRequest, HideDocumentNumberBase (+6 more)

### Community 15 - "Community 15"
Cohesion: 0.14
Nodes (14): HttpRequest, HttpResponse, HttpRequest, HttpResponse, HttpRequest, HttpResponse, handle(), DELETE /api/master/gl-group/delete  Hard delete by gl_code (single PK). Locked d (+6 more)

### Community 16 - "Community 16"
Cohesion: 0.31
Nodes (15): cc_delete_route(), cc_list_route(), cc_reference_route(), cc_save_route(), delete_route(), hd_delete_route(), hd_list_route(), hd_save_route() (+7 more)

### Community 17 - "Community 17"
Cohesion: 0.18
Nodes (7): make_request(), Unit tests for GL Group Master handlers.  Mocks pyodbc helpers + auth so tests r, Pydantic regex validation rejects non-digit gl_code, Fail Fast: locked decision #5, create_on_save: new group_name → INSERT dim, then mapping, TestListHandler, TestSaveHandler

### Community 18 - "Community 18"
Cohesion: 0.15
Nodes (12): _c(), left(), leftof(), Render the Budget Closing Date MODULE page (demo) to screenshots + measure marke, Marker at left margin, leader pointing right into element's left edge., Marker sits just left of a right-aligned element., Marker above element, leader pointing down into it., top() (+4 more)

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (4): build(), PDF, Generate Approval Workflow Spec PDF (sign-off version) Usage: python requirement, FPDF

### Community 20 - "Community 20"
Cohesion: 0.22
Nodes (9): HttpRequest, HttpResponse, main(), Standalone test for validate_docs_handler.validate().  Bypasses Azure Function r, run(), handle(), POST /api/master/hide-document/validate-docs  Body:    { "codes": ["5400005042",, Pure logic — testable without the Function runtime. (+1 more)

### Community 21 - "Community 21"
Cohesion: 0.22
Nodes (8): _allowed_emails(), authenticate(), SWA principal header auth with email allowlist.  Reads ADMIN_EMAILS env var (com, Read SWA-injected headers, check email allowlist. Raise AuthError on failure., HttpRequest, HttpResponse, handle(), GET /api/master/orgcode-costcenter/reference/{ref_name}  ref_name = orgcodes

### Community 22 - "Community 22"
Cohesion: 0.24
Nodes (6): AuthError, HttpRequest, HttpResponse, TestDeleteHandler, handle(), POST /api/master/orgcode-costcenter/save

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (9): apply_edits(), esc(), expand(), load(), main(), rPr of the text run with the most characters (dominant style)., rebuild_para(), rpr_template() (+1 more)

### Community 24 - "Community 24"
Cohesion: 0.28
Nodes (8): Path, check(), main(), Smoke test for 0008 Hide Document Number page (multi-chip + free-text + validate, # IMPORTANT: clear via JS to avoid Backspace popping a chip, Serve `directory` over HTTP on a random localhost port. Returns (server, port)., start_static_server(), TCPServer

### Community 25 - "Community 25"
Cohesion: 0.39
Nodes (8): apply_text_edits(), esc(), expand(), insert_rows(), load(), main(), run_span(), write_docx()

### Community 26 - "Community 26"
Cohesion: 0.36
Nodes (5): check(), main(), MockReq, parse(), E2E test: invoke hide-document handlers against the real Fabric SQL DB.  Bypasse

### Community 28 - "Community 28"
Cohesion: 0.46
Nodes (7): _b64(), build_attachments(), build_message(), get_token(), main(), Send Budget Management Web monthly progress report via Microsoft Graph sendMail., send()

### Community 29 - "Community 29"
Cohesion: 0.57
Nodes (7): card(), esc(), files_row(), fileurl(), fmt(), main(), ISO -> human, e.g. '28 June 2026 7:23 PM'. Falls back to raw on parse error.

### Community 30 - "Community 30"
Cohesion: 0.43
Nodes (6): Exception, emp_to_dict(), fetch_from_api(), get_conn(), sync_employees.py — Daily sync: C-POP HR API -> Fabric SQL DB (mas_employee_data, sync()

### Community 31 - "Community 31"
Cohesion: 0.48
Nodes (6): build_attachments(), confirm_mailbox(), get_token(), main(), Send sign-off spec docs to reviewer via Microsoft Graph sendMail.  Uses the exis, send()

### Community 32 - "Community 32"
Cohesion: 0.40
Nodes (4): HttpRequest, HttpResponse, handle(), GET /api/master/gl-group/list  Returns all mappings joined with dim table so fro

### Community 33 - "Community 33"
Cohesion: 0.40
Nodes (4): HttpRequest, HttpResponse, handle(), GET /api/master/hide-document/list  Returns all (doc_num, fiscal_year, fiscal_mo

### Community 34 - "Community 34"
Cohesion: 0.40
Nodes (4): HttpRequest, HttpResponse, handle(), GET /api/master/orgcode-costcenter/list

### Community 35 - "Community 35"
Cohesion: 0.60
Nodes (4): get_conn(), load_xlsx(), main(), Seed cfg_master.orgcode_costcenter_map from docs/09orgcode & costcenter.xlsx Usa

### Community 38 - "Community 38"
Cohesion: 0.50
Nodes (4): Assign each run a module index by watching for 'ส่วน C ... หน้า:' title runs., runs(), segment(), unescape()

### Community 39 - "Community 39"
Cohesion: 0.67
Nodes (3): get_connection(), test_connection(), Connection

### Community 40 - "Community 40"
Cohesion: 0.83
Nodes (3): main(), prot(), words()

### Community 41 - "Community 41"
Cohesion: 0.67
Nodes (3): main(), Return dict of protected-token-kind -> list, extracted from text t., tokens()

### Community 42 - "Community 42"
Cohesion: 0.83
Nodes (3): load_xml(), main(), write_docx()

### Community 43 - "Community 43"
Cohesion: 0.83
Nodes (3): body_text(), metrics(), q()

## Knowledge Gaps
- **16 isolated node(s):** `glApiClient`, `occApiClient`, `sapGlCodes`, `glGroupDims`, `masterData` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AuthError` connect `Community 22` to `Community 32`, `Community 0`, `Community 33`, `Community 34`, `Community 1`, `Community 15`, `Community 17`, `Community 20`, `Community 21`, `Community 30`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `authenticate()` connect `Community 21` to `Community 32`, `Community 0`, `Community 33`, `Community 34`, `Community 15`, `Community 20`, `Community 22`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `execute()` connect `Community 0` to `Community 22`, `Community 15`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `AuthError` (e.g. with `HttpRequest` and `HttpResponse`) actually correct?**
  _`AuthError` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `authenticate()` (e.g. with `handle()` and `handle()`) actually correct?**
  _`authenticate()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `execute()` (e.g. with `_delete_test_group()` and `_delete_test_row()`) actually correct?**
  _`execute()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `glApiClient`, `occApiClient`, `sapGlCodes` to the rest of the system?**
  _132 weakly-connected nodes found - possible documentation gaps or missing edges._