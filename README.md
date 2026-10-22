# HTML Table to JSON Parser for AI Agents

A small HTTP API that fetches a **public HTML webpage** and returns its HTML tables as JSON. It uses FastAPI and pandas; it does not call a paid AI API and does not require an API key.

**Hosted API:** https://table-parser-api-rov-entra.onrender.com  
**Interactive docs:** https://table-parser-api-rov-entra.onrender.com/docs  
**OpenAPI schema:** https://table-parser-api-rov-entra.onrender.com/openapi.json  
**Health check:** https://table-parser-api-rov-entra.onrender.com/health  
**Remote MCP endpoint:** https://table-parser-api-rov-entra.onrender.com/mcp  
**AI agent integration guide:** [AI_AGENT_INTEGRATION.md](AI_AGENT_INTEGRATION.md)  
**Optional local MCP adapter:** [integrations/mcp/README.md](integrations/mcp/README.md)

## Quick start

Send a POST request to `/api/v1/extract-tables` with a JSON body:

```bash
curl -X POST "https://table-parser-api-rov-entra.onrender.com/api/v1/extract-tables" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"url":"https://www.w3schools.com/html/html_tables.asp"}'
```

Example response shape:

```json
{
  "url": "https://www.w3schools.com/html/html_tables.asp",
  "tables_found": 2,
  "tables": [
    [
      {
        "Company": "Alfreds Futterkiste",
        "Contact": "Maria Anders",
        "Country": "Germany"
      }
    ]
  ]
}
```

The number of tables and records depends on the source page.

For ready-to-run Python, JavaScript, and cURL examples, agent tool instructions, and error-handling guidance, see the [AI agent integration guide](AI_AGENT_INTEGRATION.md).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | API information, links and processing limits |
| GET | `/health` | Lightweight health status |
| POST | `/api/v1/extract-tables` | Extract HTML tables as JSON |
| MCP Streamable HTTP | `/mcp` | Remote AI-agent tools: table extraction and service information |
| GET | `/docs` | Interactive Swagger UI |
| GET | `/openapi.json` | OpenAPI schema for compatible tools and AI agents |

## Input

```json
{
  "url": "https://example.com/page-with-a-table"
}
```

The target must be a publicly accessible HTTP or HTTPS webpage. Local/private hostnames, credentials embedded in URLs, and ports other than 80 or 443 are rejected.

## Processing limits

- Source HTML: 2 MiB maximum
- Redirects: 3 maximum; each destination is validated
- Tables per page: 20 maximum
- Rows per table: 5,000 maximum
- Columns per table: 100 maximum
- Total table cells: 100,000 maximum
- Request timeout: 3 seconds to connect, 10 seconds to read

These limits help keep the free service usable and limit excessive resource consumption.

## Important limitations

- The parser reads the HTML returned by the website. Tables created only by JavaScript after the page loads may not be available.
- Some sites block automated requests, require login, or may return incomplete content.
- The hosted REST and MCP endpoints run on the same Render service, so your computer does not need to remain on. The free hosting instance may sleep after 15 minutes without incoming traffic; the first request afterward can take about a minute to wake up.
- The API is currently unauthenticated and has no per-user quota. Keep usage reasonable; additional abuse protection should be added before promoting it to a large public audience.
- Do not submit internal URLs, private pages, credentials, or confidential data.

## Run locally

Install the dependencies and start FastAPI:

```bash
python -m pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Then visit http://127.0.0.1:8000/docs.

## Cost

The application itself does not use paid AI models or paid API providers. Hosting remains subject to the selected hosting provider's free-tier limits. This repository does not guarantee uninterrupted or always-on hosting.
