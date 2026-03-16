/**
 * VehicleLayer — Renders vehicles as glowing 3D boxes with neon trails using Deck.GL
 */
import { useEffect, useRef } from 'react';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PolygonLayer, TextLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import maplibregl from 'maplibre-gl';

// --- Constants & Colors ---
const TRAM_COLORS = {
  '1': '#E2001A', '2': '#00A650', '3': '#F39200', '4': '#E2001A',
  '6': '#009FE3', '7': '#CE1266', '8': '#009640', '9': '#A62B44',
  '10': '#006AB3', '11': '#EE7F00', '12': '#A12944', '13': '#8B6E45',
};

function hexToRgb(hex) {
  const c = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return c ? [parseInt(c[1], 16), parseInt(c[2], 16), parseInt(c[3], 16)] : [200, 200, 200];
}

function getVehicleColorArray(vehicle) {
  if (vehicle.is_stale) return [136, 136, 136];
  if (vehicle.mode === 'Tram' && TRAM_COLORS[vehicle.line_id]) {
    return hexToRgb(TRAM_COLORS[vehicle.line_id]);
  }
  if (vehicle.mode === 'Tram') return [245, 173, 85];
  return [34, 211, 238]; // Bus cyan
}

// --- Math & Interpolation ---
function getVehiclePolygon(lon, lat, heading, mode) {
  const length = mode === 'Tram' ? 48 : 12; // Trams are 2x longer (was 24, now 48)
  const width = mode === 'Tram' ? 2.5 : 2.8;

  const latRatio = 1 / 111111;
  const lonRatio = 1 / (111111 * Math.cos((lat * Math.PI) / 180));
  
  const hdgRad = (heading * Math.PI) / 180;
  
  const l = length / 2;
  const w = width / 2;

  // 4 corners relative to center
  const corners = [
    [-w, l], // FL
    [w, l],  // FR
    [w, -l], // BR
    [-w, -l] // BL
  ];

  return corners.map(([cx, cy]) => [
    (cx * Math.cos(hdgRad) + cy * Math.sin(hdgRad)) * lonRatio + lon,
    (-cx * Math.sin(hdgRad) + cy * Math.cos(hdgRad)) * latRatio + lat
  ]);
}

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (v) => (v * Math.PI) / 180;
  const a = Math.sin(toRad(lat2 - lat1) / 2) ** 2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lon2 - lon1) / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function bearing(lat1, lon1, lat2, lon2) {
  const toRad = (v) => (v * Math.PI) / 180;
  const toDeg = (v) => (v * 180) / Math.PI;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
            Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

function interpolatePolyline(polyline, progress) {
  if (!polyline || polyline.length === 0) return { lat: 0, lon: 0, heading: 0 };
  if (polyline.length === 1) return { lat: polyline[0][0], lon: polyline[0][1], heading: 0 };

  const p = Math.max(0, Math.min(1, progress));
  const dists = [0];
  for (let i = 1; i < polyline.length; i++) {
    dists.push(dists[i - 1] + haversine(polyline[i - 1][0], polyline[i - 1][1], polyline[i][0], polyline[i][1]));
  }
  const total = dists[dists.length - 1];
  if (total === 0) return { lat: polyline[0][0], lon: polyline[0][1], heading: 0 };

  const target = p * total;
  for (let i = 1; i < dists.length; i++) {
    if (dists[i] >= target) {
      const segStart = dists[i - 1];
      const segLen = dists[i] - segStart;
      const t = segLen > 0 ? (target - segStart) / segLen : 0;
      const lat = polyline[i - 1][0] + t * (polyline[i][0] - polyline[i - 1][0]);
      const lon = polyline[i - 1][1] + t * (polyline[i][1] - polyline[i - 1][1]);
      const head = bearing(polyline[i - 1][0], polyline[i - 1][1], polyline[i][0], polyline[i][1]);
      return { lat, lon, heading: head };
    }
  }

  const last = polyline[polyline.length - 1];
  const prev = polyline[polyline.length - 2];
  return { lat: last[0], lon: last[1], heading: bearing(prev[0], prev[1], last[0], last[1]) };
}

// --- Polyline to Trips Path (Reversing [lat, lon] to [lon, lat]) ---
function buildTripData(stateId, s, now) {
  if (!s.polyline || s.polyline.length < 2) return null;
  
  const path = s.polyline.map(p => [p[1], p[0]]);
  
  const dists = [0];
  for (let i = 1; i < s.polyline.length; i++) {
    dists.push(dists[i - 1] + haversine(s.polyline[i - 1][0], s.polyline[i - 1][1], s.polyline[i][0], s.polyline[i][1]));
  }
  const total = dists[dists.length - 1];
  
  // Calculate when this vehicle started the current segment (in absolute ms)
  const durationMs = s.segmentDuration * 1000;
  
  // If progress is 0.5 and duration is 60s, it started 30s ago
  const segmentStartTime = now - (s.clientProgress * durationMs);
  
  // Map distances to absolute timestamps
  const timestamps = dists.map(d => segmentStartTime + (total > 0 ? (d / total) * durationMs : 0));
  
  return {
    path,
    timestamps,
    color: s.colorArray
  };
}

// ------------------------------------------------------------------
// Main Component
// ------------------------------------------------------------------
export default function VehicleLayer({ map, vehicles }) {
  const overlayRef = useRef(null);
  const stateRef = useRef({ vehicles: {} });
  const animationRef = useRef(null);

  const handleVehicleClick = (info) => {
    if (!info || !info.object) return;
    const v = info.object;
    
    const delay = v.delay_seconds || 0;
    let delayText = 'On time', delayClass = 'on-time';
    if (delay > 300) { delayText = `+${Math.round(delay / 60)} min late`; delayClass = 'very-delayed'; }
    else if (delay > 60) { delayText = `+${Math.round(delay / 60)} min late`; delayClass = 'delayed'; }

    const cssColor = `rgba(${v.color[0]}, ${v.color[1]}, ${v.color[2]}, 1)`;

    const popups = document.querySelectorAll('.maplibregl-popup');
    popups.forEach(p => p.remove());
    
    try {
      new maplibregl.Popup({ offset: 20, closeButton: true })
        .setLngLat([v.lon, v.lat])
        .setHTML(`
          <div class="vehicle-popup">
            <div class="vehicle-popup-header">
              <span class="vehicle-popup-line" style="background:${cssColor}">${v.label}</span>
              <span class="vehicle-popup-mode">${v.mode}</span>
            </div>
            <div class="vehicle-popup-direction">→ ${v.direction}</div>
            <div class="vehicle-popup-delay ${delayClass}">${delayText}</div>
            <div class="vehicle-popup-stop">${v.prev_stop} → ${v.next_stop}</div>
          </div>
        `)
        .addTo(map);
    } catch (err) {
      console.error("Popup Error:", err);
    }
  };

  // 1. Initialize Deck.GL MapboxOverlay
  useEffect(() => {
    if (!map || overlayRef.current) return;

    overlayRef.current = new MapboxOverlay({
      interleaved: true,
      layers: []
    });
    
    // Add underneath water/labels if possible, otherwise standard addControl
    map.addControl(overlayRef.current);

    // CRITICAL DECK.GL MAPBOX PICKING FIX:
    // Mapbox/MapLibre often swallows pointer events. We must manually 
    // force DeckGL to pick on map clicks if the native interleaved picking fails.
    const mapClickListener = (e) => {
      if (overlayRef.current) {
        // Increase picking radius significantly for reliable selection on moving objects
        const pickInfo = overlayRef.current.pickObject({
          x: e.point.x,
          y: e.point.y,
          radius: 25 // Much larger hitting area
        });
        if (pickInfo && pickInfo.object) {
          handleVehicleClick(pickInfo);
        }
      }
    };
    
    map.on('click', mapClickListener);

    return () => {
      if (map) {
        map.off('click', mapClickListener);
        if (overlayRef.current) {
          map.removeControl(overlayRef.current);
        }
      }
      overlayRef.current = null;
    };
  }, [map]);

  // 2. Process incoming server data
  useEffect(() => {
    if (!map) return;
    const state = stateRef.current.vehicles;

    vehicles.forEach(v => {
      const id = v.vehicle_id;
      const colorArray = getVehicleColorArray(v);

      if (!state[id]) {
        state[id] = {
          lat: v.lat,
          lon: v.lon,
          heading: v.heading || 0,
          prevLat: v.prev_stop_lat,
          prevLon: v.prev_stop_lon,
          nextLat: v.next_stop_lat,
          nextLon: v.next_stop_lon,
          segmentDuration: v.segment_duration_seconds || 180,
          serverProgress: v.progress || 0,
          polyline: v.polyline,
          clientProgress: v.progress || 0,
          progressRate: v.segment_duration_seconds > 0 ? 1 / v.segment_duration_seconds : 0,
          lastUpdateTime: performance.now(),
          colorArray,
          mode: v.mode,
          is_stale: v.is_stale || false,
          label: v.line_id || '',
          direction: v.direction || '',
          delay_seconds: v.delay_seconds || 0,
          prev_stop: v.prev_stop || '',
          next_stop: v.next_stop || ''
        };
      } else {
        const s = state[id];
        s.prevLat = v.prev_stop_lat ?? s.prevLat;
        s.prevLon = v.prev_stop_lon ?? s.prevLon;
        s.nextLat = v.next_stop_lat ?? s.nextLat;
        s.nextLon = v.next_stop_lon ?? s.nextLon;
        s.segmentDuration = v.segment_duration_seconds || s.segmentDuration;
        s.serverProgress = v.progress || 0;
        s.polyline = v.polyline || s.polyline;
        
        const timeRemaining = (1.0 - s.serverProgress) * s.segmentDuration;
        const safeTimeRemaining = Math.max(1.0, timeRemaining); 
        
        if (s.serverProgress >= 1 || s.serverProgress <= 0) {
            s.clientProgress = s.serverProgress; 
            s.progressRate = 0;
        } else {
            s.progressRate = (1.0 - s.clientProgress) / safeTimeRemaining;
        }
        
        s.heading = v.heading || s.heading;
        s.colorArray = colorArray;
        s.mode = v.mode;
        s.is_stale = v.is_stale || false;
        s.label = v.line_id || s.label;
        s.direction = v.direction || s.direction;
        s.delay_seconds = v.delay_seconds !== undefined ? v.delay_seconds : s.delay_seconds;
        s.prev_stop = v.prev_stop || s.prev_stop;
        s.next_stop = v.next_stop || s.next_stop;
      }
    });

    const activeIds = new Set(vehicles.map(v => v.vehicle_id));
    Object.keys(state).forEach(id => {
      if (!activeIds.has(id)) delete state[id];
    });
  }, [vehicles, map]);

  // 3. Continuous Animation Loop pushing to Deck.GL
  useEffect(() => {
    if (!map) return;
    let running = true;

    function renderFrame() {
      if (!running) return;

      const now = performance.now();
      const state = stateRef.current.vehicles;
      const zoom = map.getZoom();
      
      // Threshold for "scrolled away like 50m range marker". 
      // Zoom 17.0 typically corresponds to the 50m-100m scale bar.
      const labelsVisible = zoom > 17.0; 
      
      const boxes = [];
      const trips = [];
      
      const occupiedPositions = []; // Track lat/lon to prevent overlaps in this frame

      Object.entries(state).forEach(([id, s]) => {
        const elapsed = (now - s.lastUpdateTime) / 1000;
        s.lastUpdateTime = now;

        if (!s.is_stale) {
            s.clientProgress += elapsed * s.progressRate;
            s.clientProgress = Math.min(1.0, Math.max(0.0, s.clientProgress));
        }

        let lat, lon, heading;

        if (s.polyline && s.polyline.length >= 2) {
          const result = interpolatePolyline(s.polyline, s.clientProgress);
          lat = result.lat;
          lon = result.lon;
          heading = result.heading;
          
          // Generate neon trail 
          const tripData = buildTripData(id, s, now);
          if (tripData) trips.push(tripData);

        } else if (s.prevLat && s.nextLat) {
          lat = s.prevLat + (s.nextLat - s.prevLat) * s.clientProgress;
          lon = s.prevLon + (s.nextLon - s.prevLon) * s.clientProgress;
          heading = s.heading;
          
          // Generate a simple straight line trail if no polyline
          const durationMs = s.segmentDuration * 1000;
          const segmentStartTime = now - (s.clientProgress * durationMs);
          trips.push({
            path: [[s.prevLon, s.prevLat], [s.nextLon, s.nextLat]],
            timestamps: [segmentStartTime, segmentStartTime + durationMs],
            color: s.colorArray
          });
        } else {
          lat = s.lat;
          lon = s.lon;
          heading = s.heading;
        }

        // Save back for next frame
        s.lat = lat;
        s.lon = lon;
        s.heading = heading;

        // --- Client-side Spacing Spread (Anti-Collision) ---
        // Prevents vehicles from stacking on top of each other at stops
        let finalLat = lat;
        let finalLon = lon;
        let overlapCount = 0;

        for (const pos of occupiedPositions) {
          const dist = haversine(finalLat, finalLon, pos.lat, pos.lon);
          if (dist < 50) { // 50m detection radius
            overlapCount++;
          }
        }

        if (overlapCount > 0) {
          // Apply a deterministic offset to fan out (approx 45m shift)
          const angle = (overlapCount - 1) * 45;
          const rad = (angle * Math.PI) / 180;
          const offsetLat = Math.cos(rad) * 0.0004;
          const offsetLon = Math.sin(rad) * 0.0004;
          finalLat += offsetLat;
          finalLon += offsetLon;
        }
        
        occupiedPositions.push({ lat: finalLat, lon: finalLon });

        // Generate glowing 3D box
        const height = s.mode === 'Tram' ? 4.5 : 3.5;
        const polygon = getVehiclePolygon(finalLon, finalLat, heading, s.mode);
        
        boxes.push({
          id, // Needed for picking
          polygon,
          elevation: height,
          color: s.colorArray,
          label: s.label,
          mode: s.mode,
          direction: s.direction,
          delay_seconds: s.delay_seconds || 0,
          prev_stop: s.prev_stop || '',
          next_stop: s.next_stop || '',
          lon: finalLon,
          lat: finalLat
        });
      });

      // Provide updated layers to Deck.GL
      if (overlayRef.current) {
        overlayRef.current.setProps({
          layers: [
            new TripsLayer({
              id: 'neon-trails-layer',
              data: trips,
              getPath: d => d.path,
              getTimestamps: d => d.timestamps,
              getColor: d => [...d.color, 255],
              opacity: 0.8,
              widthMinPixels: 4,
              rounded: true,
              fadeTrail: true,
              trailLength: 20000, // Trail fades over 20 seconds
              currentTime: now, // Global absolute time
            }),
            new PolygonLayer({
              id: '3d-vehicles-layer',
              data: boxes,
              getPolygon: d => d.polygon,
              getElevation: d => d.elevation,
              getFillColor: d => [...d.color, 240],
              extruded: true,
              wireframe: true,
              getLineColor: d => [...d.color, 255],
              lineWidthMinPixels: 2,
              pickable: true,
              autoHighlight: true,
              highlightColor: [255, 255, 255, 100],
              onClick: handleVehicleClick
            }),
            new TextLayer({
              id: 'vehicle-labels-layer',
              data: boxes,
              visible: labelsVisible, // DISSAPEAR WHEN SCROLLED AWAY (Zoom < 17.0)
              getPosition: d => [d.lon, d.lat, d.elevation + 2], // Floating 2m above the roof
              getText: d => d.label,
              getSize: 12, // Subtler size
              sizeUnits: 'pixels',
              sizeScale: 1, 
              sizeMinPixels: 0, 
              sizeMaxPixels: 14, 
              getColor: d => [255, 255, 255, 255],
              getBackgroundColor: d => [...d.color, 200],
              backgroundPadding: [4, 2, 4, 2],
              fontFamily: 'Space Grotesk, sans-serif',
              fontWeight: 700,
              billboard: true,
              background: true,
              getOffset: [0, -10],
              pickable: true,
              autoHighlight: true,
              onClick: handleVehicleClick
            })
          ]
        });
        
        // Ensure cursor updates when hovering vehicles via Deck.GL
        overlayRef.current.setProps({
          getCursor: ({isHovering}) => isHovering ? 'pointer' : 'grab'
        });
      }

      animationRef.current = requestAnimationFrame(renderFrame);
    }

    animationRef.current = requestAnimationFrame(renderFrame);

    return () => {
      running = false;
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [map]);

  return null;
}
