/**
 * useVehicles — React hook that combines REST initial load with WebSocket updates.
 * Also provides client-side interpolation targets for smooth animation.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchVehicles } from '../services/api';
import useWebSocket from './useWebSocket';

export default function useVehicles() {
  const [vehicles, setVehicles] = useState([]);
  const { vehicles: wsVehicles, connected } = useWebSocket();
  const initialLoaded = useRef(false);

  // Initial REST load
  useEffect(() => {
    async function load() {
      try {
        const data = await fetchVehicles();
        if (Array.isArray(data) && data.length > 0) {
          setVehicles(data);
          initialLoaded.current = true;
        }
      } catch (err) {
        console.warn('[Vehicles] Initial fetch failed:', err);
      }
    }
    load();
  }, []);

  // Update from WebSocket when new data arrives
  useEffect(() => {
    if (wsVehicles.length > 0) {
      setVehicles(wsVehicles);
      initialLoaded.current = true;
    }
  }, [wsVehicles]);

  // Fallback: poll REST every 10s if WebSocket is disconnected
  useEffect(() => {
    if (connected) return; // WS is handling updates

    const interval = setInterval(async () => {
      try {
        const data = await fetchVehicles();
        if (Array.isArray(data)) setVehicles(data);
      } catch (err) {
        // Silently retry
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [connected]);

  // Count by mode
  const tramCount = vehicles.filter(v => v.mode === 'Tram').length;
  const busCount = vehicles.filter(v => v.mode !== 'Tram').length;

  return {
    vehicles,
    connected,
    tramCount,
    busCount,
    totalCount: vehicles.length,
  };
}
