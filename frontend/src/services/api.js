/**
 * API client — fetches data from the FastAPI backend via the Vite proxy.
 */

// All API calls go through the Vite proxy (/api -> localhost:8000/api)
const BASE_URL = '/api';

/**
 * Fetch all DVB stops.
 * @returns {Promise<Array>} Array of stop objects
 */
export async function fetchStops() {
  const response = await fetch(`${BASE_URL}/stops`);
  if (!response.ok) throw new Error(`Failed to fetch stops: ${response.status}`);
  return response.json();
}

/**
 * Fetch all DVB lines.
 * @returns {Promise<Array>} Array of line objects
 */
export async function fetchLines() {
  const response = await fetch(`${BASE_URL}/lines`);
  if (!response.ok) throw new Error(`Failed to fetch lines: ${response.status}`);
  return response.json();
}

/**
 * Fetch current vehicle positions.
 * @returns {Promise<Array>} Array of vehicle objects
 */
export async function fetchVehicles() {
  const response = await fetch(`${BASE_URL}/vehicles`);
  if (!response.ok) throw new Error(`Failed to fetch vehicles: ${response.status}`);
  return response.json();
}
