// Ports for the two real stacks the e2e suite starts. Set E2E_PORT_OFFSET=100 to avoid clashing with a dev stack already on 8000/5173.
const off = Number(process.env.E2E_PORT_OFFSET ?? 0);
export const PORTS = { apiA: 8000 + off, apiB: 8001 + off, uiA: 5173 + off, uiB: 5174 + off };
export const UI_A = `http://127.0.0.1:${PORTS.uiA}`;
export const UI_B = `http://127.0.0.1:${PORTS.uiB}`;
export const API_A = `http://127.0.0.1:${PORTS.apiA}`;
export const COORD = "e2e-coordinator-token"; // throw-away test value
