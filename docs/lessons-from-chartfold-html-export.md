# Lessons from Chartfold's Single-File HTML SPA Export

Chartfold exports a patient's entire clinical database as a **single self-contained HTML file** that runs as a full SPA in the browser. No server needed. No dependencies. Just open the file. Here's what we learned building it, and ideas for where this pattern could go.

## The Core Trick: Embedded SQLite via WebAssembly

The entire SQLite database is embedded inside the HTML file as a base64-encoded, gzip-compressed blob:

```html
<script id="chartfold-db" type="application/gzip+base64">H4sIAAAAA...</script>
<script id="sqljs-wasm" type="application/base64">AGFzbQ...</script>
```

At load time, the JS:
1. Reads the base64 string from the `<script>` tag
2. Decompresses using the browser's native `DecompressionStream` API (no pako.js needed!)
3. Initializes sql.js (SQLite compiled to WebAssembly)
4. Opens the decompressed bytes as an in-memory database

```javascript
// Decode base64 to bytes
var compressed = Uint8Array.from(atob(b64), function(c) { return c.charCodeAt(0); });

// Decompress using native browser API (no library needed)
var ds = new DecompressionStream('gzip');
var writer = ds.writable.getWriter();
writer.write(compressed);
writer.close();
var reader = ds.readable.getReader();
var chunks = [];
while (true) {
  var { done, value } = await reader.read();
  if (done) break;
  chunks.push(value);
}
// ... concatenate chunks into a single Uint8Array

var SQL = await initSqlJs({ wasmBinary: wasmBinary });
var db = new SQL.Database(dbBytes);
```

**Key discovery**: Modern browsers (Chrome 80+, Firefox 113+, Safari 16.4+) have native `DecompressionStream` — no need for pako.js or any third-party decompression library. This saves ~47 KB in the output file.

Now the browser has a fully functional SQL engine with the user's data. Every UI interaction just runs a SQL query.

## Gzip Compression Matters

A raw SQLite database can be several MB. Gzip compression at level 9 typically achieves **70-85% reduction** because SQLite files contain a lot of internal padding and repeated structures. A 4 MB database becomes ~800 KB in the HTML. The base64 encoding adds ~33% overhead, but you're still way ahead of raw.

The WASM binary (sql-wasm.wasm, ~1 MB) is **not** gzipped because it's already compressed by the WebAssembly compiler. Base64 encoding it directly is the right call.

## Single-File Architecture

Everything in one HTML file:
- **CSS**: Inlined in a `<style>` block
- **JavaScript**: All app JS concatenated and inlined in a `<script>` block
- **SQL.js loader**: The sql-wasm.js library inlined as a `<script>`
- **WASM binary**: Base64-encoded in a `<script type="application/base64">`
- **Database**: Gzip+base64 in a `<script type="application/gzip+base64">`
- **Config**: JSON in a `<script type="application/json">`
- **Images**: Optional base64 data URIs in a JSON blob (can add significant size)

The Python export function reads all these pieces and string-formats them into the HTML template. The result is a single `.html` file that can be emailed, put on a USB drive, or hosted on a static site.

## Key Safety Patterns

### Script Tag Escaping
JSON embedded inside `<script>` tags must escape `</` to prevent premature tag closing:
```python
def _safe_json_for_script(json_str):
    return json_str.replace("</", "<\\/")
```

### SQL Injection Prevention
The SQL console in the SPA blocks write operations client-side:
```javascript
var forbidden = /\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|PRAGMA|ATTACH|DETACH)\b/i;
if (forbidden.test(sql)) { /* reject */ }
```

### XSS in Markdown
The embedded markdown renderer sanitizes links:
```javascript
// Only allow http/https/mailto protocols
if (!/^(https?:|mailto:)/i.test(url)) return '[link]';
```

## The "Fully Fledged App" Vision

Here's where it gets interesting. If a single HTML file can contain:
- A full SQL database with client-side query engine
- A SPA with routing, charts, search, filtering
- Embedded images and documents

Then why not also embed:
- **An AI chat interface** that calls OpenAI/Claude/etc APIs directly from the browser? The user provides their API key (stored in localStorage), and the LLM can query the embedded SQLite database via tool use / function calling. The HTML export becomes a **portable AI-powered medical record viewer**.
- **An MCP client** that connects to MCP servers? If the HTML file runs as a local file or on a static site, it could potentially connect to localhost MCP servers or remote ones via SSE/WebSocket. The exported file becomes a **full MCP host** — your data + AI + tools, all from a single file.

### Practical Steps Toward This

1. **AI Chat Panel**: Add a chat sidebar to the SPA. On first use, prompt for an API key (OpenAI or Anthropic). Store in localStorage. Send messages to the API with a system prompt that includes the database schema. When the LLM wants to query data, execute SQL client-side and return results. This is entirely client-side — no server needed.

2. **Tool Use / Function Calling**: Define tools like `query_database(sql)`, `get_lab_trend(test_name)`, `get_medications()`. The LLM calls these, the JS executes them against the embedded SQLite, and returns results. The LLM can then reason about the patient's data.

3. **MCP Client in Browser**: An MCP client is just HTTP (SSE for server-sent events, or WebSocket). A browser JS client could connect to `localhost:3000` or any remote MCP server. The SPA becomes an MCP host that exposes its embedded database as MCP resources/tools.

4. **Static Blog Deployment**: The HTML file works on any static hosting (GitHub Pages, Netlify, S3). If it includes an MCP client, you could host MCP servers alongside it or point to remote ones. Your "static blog" becomes a fully interactive application platform.

### Security Considerations
- API keys stored in localStorage are accessible to any JS on the page. For a single-file export opened locally, this is fine. For hosted versions, consider the trust model.
- MCP connections from a static site would need CORS support on the server side.
- The database is fully client-side — no data leaves the browser unless the user explicitly sends it to an AI API.

## What This Means for CTK

CTK could use the same pattern for conversation exports:
- Embed conversation data as a compressed SQLite database
- Render a browsable, searchable conversation viewer in a single HTML file
- Add an AI chat interface that can reference and reason about the conversation data
- Potentially embed MCP client capabilities for connecting to external tools

The pattern generalizes to: **any structured data + a query engine + a UI + optional AI = a portable, self-contained application**.

## Technical Details

| Component | Size (typical) | Notes |
|-----------|---------------|-------|
| sql-wasm.wasm | ~1 MB (base64: ~1.3 MB) | WebAssembly SQLite engine |
| sql-wasm.js | ~60 KB | JS loader/wrapper |
| DecompressionStream | 0 KB (native) | Browser-native gzip decompression |
| App JS (all files) | ~30 KB | SPA code (sections, router, UI, charts) |
| CSS | ~15 KB | Apple Health-inspired styles |
| Database | varies | Gzip + base64: typically 15-30% of raw size |

Total overhead for the "engine" is about 1.5 MB. The rest is data.

## Vendor Libraries

- **sql.js**: SQLite compiled to WebAssembly. MIT license. https://github.com/sql-js/sql.js
- **DecompressionStream**: Native browser API for gzip decompression. No library needed. Supported in all modern browsers since 2023.

---
*Written 2026-02-16 based on chartfold SPA export implementation*
