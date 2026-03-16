/**
 * MapView — Initializes MapLibre GL JS with 3D buildings and terrain.
 * 
 * Uses OpenFreeMap (free, no API key) for vector tiles and styles.
 * Adds 3D building extrusions from OpenStreetMap data.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';

// Dresden centre
const INITIAL_CENTER = [13.7373, 51.0504]; // [lng, lat] for MapLibre
const INITIAL_ZOOM = 13;
const INITIAL_PITCH = 50;
const INITIAL_BEARING = -15;

// Bounding box around Dresden — prevents panning to other cities
const DRESDEN_BOUNDS = [
  [13.55, 50.95],  // Southwest corner
  [13.95, 51.15],  // Northeast corner
];

export default function MapView({ onMapReady, children }) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  useEffect(() => {
    if (mapRef.current) return; // Already initialized

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      // OpenFreeMap — free vector tiles, no API key needed
      style: 'https://tiles.openfreemap.org/styles/dark',
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      pitch: INITIAL_PITCH,
      bearing: INITIAL_BEARING,
      maxPitch: 70,
      minZoom: 11,
      maxBounds: DRESDEN_BOUNDS,
      antialias: true,
      attributionControl: true,
    });

    // Navigation controls (zoom, rotate, compass)
    map.addControl(new maplibregl.NavigationControl({
      showCompass: true,
      showZoom: true,
      visualizePitch: true,
    }), 'bottom-right');

    // Scale bar
    map.addControl(new maplibregl.ScaleControl({
      maxWidth: 150,
      unit: 'metric',
    }), 'bottom-left');

    map.on('style.load', () => {
      // Force center to Dresden to override any style defaults
      map.jumpTo({
        center: INITIAL_CENTER,
        zoom: INITIAL_ZOOM,
        pitch: INITIAL_PITCH,
        bearing: INITIAL_BEARING,
      });

      // Add 3D building extrusions
      add3DBuildings(map);
      
      mapRef.current = map;
      setMapLoaded(true);

      if (onMapReady) {
        onMapReady(map);
      }
    });

    // Handle persistent load issues
    map.on('error', (e) => {
      console.error('MapLibre error:', e);
    });

    return () => {
      if (map) map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <>
      <div ref={mapContainerRef} className="map-container" />
      {mapLoaded && children && typeof children === 'function'
        ? children(mapRef.current)
        : null}
    </>
  );
}

/**
 * Add 3D building extrusions to the map.
 * Checks if the style already has a building layer and extrudes it,
 * or adds a new building source + layer if needed.
 */
function add3DBuildings(map) {
  const layers = map.getStyle().layers || [];

  // Look for an existing building layer to modify
  let buildingLayerFound = false;
  for (const layer of layers) {
    if (
      layer.id.includes('building') &&
      layer.type === 'fill'
    ) {
      // Convert the flat fill layer into a 3D extrusion
      try {
        map.removeLayer(layer.id);
        map.addLayer({
          id: layer.id + '-3d',
          source: layer.source,
          'source-layer': layer['source-layer'],
          type: 'fill-extrusion',
          minzoom: 14,
          paint: {
            'fill-extrusion-color': [
              'interpolate', ['linear'], ['get', 'render_height'],
              0, '#1a1f2e',
              20, '#252b3d',
              50, '#2d3450',
            ],
            'fill-extrusion-height': [
              'interpolate', ['linear'], ['zoom'],
              14, 0,
              15.5, ['coalesce', ['get', 'render_height'], ['get', 'height'], 10],
            ],
            'fill-extrusion-base': [
              'coalesce', ['get', 'render_min_height'], 0,
            ],
            'fill-extrusion-opacity': 0.75,
          },
        });
        buildingLayerFound = true;
      } catch (e) {
        console.warn('Could not extrude building layer:', e);
      }
      break;
    }
  }

  // If no building layer found, try adding from OpenMapTiles building source
  if (!buildingLayerFound) {
    // Many vector tile styles include buildings in the 'openmaptiles' source
    const sources = map.getStyle().sources || {};
    for (const [sourceId, source] of Object.entries(sources)) {
      if (source.type === 'vector') {
        try {
          map.addLayer({
            id: 'buildings-3d',
            source: sourceId,
            'source-layer': 'building',
            type: 'fill-extrusion',
            minzoom: 14,
            paint: {
              'fill-extrusion-color': '#1a1f2e',
              'fill-extrusion-height': [
                'coalesce', ['get', 'render_height'], ['get', 'height'], 10,
              ],
              'fill-extrusion-base': [
                'coalesce', ['get', 'render_min_height'], 0,
              ],
              'fill-extrusion-opacity': 0.7,
            },
          });
          console.log('[Map] Added 3D buildings from source:', sourceId);
          break;
        } catch (e) {
          // Source might not have a building layer — that's ok
        }
      }
    }
  }
}


