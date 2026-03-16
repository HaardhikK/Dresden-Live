/**
 * useWebSocket — React hook for real-time vehicle updates via WebSocket.
 * Connects through the Vite proxy (same origin) to avoid CORS issues.
 * Auto-reconnects on disconnect with exponential backoff.
 */
import { useEffect, useRef, useState, useCallback } from 'react';

export default function useWebSocket() {
  const [vehicles, setVehicles] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectAttempts = useRef(0);

  const connect = useCallback(() => {
    try {
      // Always connect via the current host — the Vite proxy forwards
      // /ws/vehicles to the backend on port 8000 automatically.
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/vehicles`;
      console.log(`[WS] Connecting to ${wsUrl}...`);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] ✓ Connected to vehicle stream');
        setConnected(true);
        reconnectAttempts.current = 0;
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current);
          reconnectTimer.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'vehicle_update' && Array.isArray(data.vehicles)) {
            setVehicles(data.vehicles);
          }
        } catch (err) {
          console.warn('[WS] Failed to parse message:', err);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Exponential backoff: 1s, 2s, 4s, 8s, max 15s
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 15000);
        reconnectAttempts.current += 1;
        console.log(`[WS] Disconnected. Reconnecting in ${delay / 1000}s...`);
        reconnectTimer.current = setTimeout(connect, delay);
      };

      ws.onerror = (err) => {
        console.warn('[WS] Error:', err);
        ws.close();
      };
    } catch (err) {
      console.warn('[WS] Connection failed:', err);
      reconnectTimer.current = setTimeout(connect, 3000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  return { vehicles, connected };
}
