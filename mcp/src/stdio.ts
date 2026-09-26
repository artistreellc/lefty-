// Local entry point: MCP over stdio (Claude Code, Claude Desktop, any local client).
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createLeftyServer } from './server.js';

await createLeftyServer().connect(new StdioServerTransport());
