/**
 * App.jsx — Root component for the Dresden Digital Twin frontend.
 * 
 * 2D map with live vehicle overlays, stop markers, and a simulation clock.
 * No 3D vehicle models — only the map terrain/buildings use 3D.
 */
import { useState, useCallback, useEffect } from 'react';
import MapView from './components/MapView';
import VehicleLayer from './components/VehicleLayer';
import StopLayer from './components/StopLayer';
import ClockOverlay from './components/ClockOverlay';
import useVehicles from './hooks/useVehicles';

export default function App() {
  const { vehicles, connected, tramCount, busCount, totalCount } = useVehicles();
  const [mapReady, setMapReady] = useState(false);
  const [mapInstance, setMapInstance] = useState(null);
  const [startupCountdown, setStartupCountdown] = useState(90);

  useEffect(() => {
    if (startupCountdown <= 0) return;
    const t = setInterval(() => setStartupCountdown(c => c - 1), 1000);
    return () => clearInterval(t);
  }, [startupCountdown]);

  const handleMapReady = useCallback((map) => {
    setMapInstance(map);
    setMapReady(true);
  }, []);

  return (
    <div className="app-container">
      {/* Loading overlay */}
      <div className={`loading-overlay ${(mapReady && startupCountdown <= 0) ? 'hidden' : ''}`}>
        <div className="loading-spinner" />
        <div className="loading-text">
            {mapReady ? `Acquiring historical data buffer... ${startupCountdown}s remaining` : 'Initializing Dresden Digital Twin…'}
        </div>
        <div className="loading-sub">Connecting to transit network</div>
      </div>

      {/* Header */}
      <div className="header-overlay">
        <div className="header-logo">
          {/* Globe Icon */}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            <path d="M2 12h20"/>
          </svg>
        </div>
        <div className="header-title">DRESDEN LIVE</div>
      </div>

      {/* Stats row (top right) */}
      <div className="stats-panel">
        <ClockOverlay />
        <div className="stat-badge">
          <span className={`stat-dot ${connected ? 'live' : 'offline'}`} />
          <span>{connected ? 'Live (90s Delay)' : 'Connecting…'}</span>
        </div>
        {totalCount > 0 && (
          <>
            <div className="stat-badge tram-badge">
              <svg className="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="3" width="16" height="16" rx="3"/>
                <line x1="12" y1="3" x2="12" y2="0"/>
                <line x1="8" y1="19" x2="6" y2="22"/>
                <line x1="16" y1="19" x2="18" y2="22"/>
                <line x1="4" y1="12" x2="20" y2="12"/>
              </svg>
              <span className="stat-value">{tramCount}</span>
              <span>Trams</span>
            </div>
            <div className="stat-badge bus-badge">
              <svg className="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 6v6m8-6v6M2 12h20M6 18h12a4 4 0 004-4V8a4 4 0 00-4-4H6a4 4 0 00-4 4v6a4 4 0 004 4z"/>
                <circle cx="7" cy="18" r="2"/>
                <circle cx="17" cy="18" r="2"/>
              </svg>
              <span className="stat-value">{busCount}</span>
              <span>Buses</span>
            </div>
          </>
        )}
      </div>



      {/* Map + Vehicles + Stops */}
      <MapView onMapReady={handleMapReady}>
        {(map) => (
          <>
            <StopLayer map={map} />
            {startupCountdown <= 0 && <VehicleLayer map={map} vehicles={vehicles} />}
          </>
        )}
      </MapView>
    </div>
  );
}
