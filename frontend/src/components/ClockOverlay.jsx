/**
 * ClockOverlay — Shows the current Dresden time (Europe/Berlin)
 * and the data freshness indicator.
 * 
 * Fetches /api/time every 30s to calculate the delay between
 * server inference and client display.
 */
import { useState, useEffect, useRef } from 'react';

const DRESDEN_TZ = 'Europe/Berlin';

function formatDresdenTime(date) {
  return date.toLocaleTimeString('de-DE', {
    timeZone: DRESDEN_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatDresdenDate(date) {
  return date.toLocaleDateString('de-DE', {
    timeZone: DRESDEN_TZ,
    day: '2-digit',
    month: 'short',
  });
}

export default function ClockOverlay() {
  const [dresdenTime, setDresdenTime] = useState('');
  const [dresdenDate, setDresdenDate] = useState('');

  // Tick the clock every second, but delayed by 90s
  useEffect(() => {
    function tick() {
      // 90000 ms = 90 seconds delay, matching the backend simulation!
      const delayedNow = new Date(Date.now() - 90000);
      setDresdenTime(formatDresdenTime(delayedNow));
      setDresdenDate(formatDresdenDate(delayedNow));
    }

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="clock-overlay">
      <div className="clock-time">{dresdenTime}</div>
      <div className="clock-meta">
        <span className="clock-date">{dresdenDate}</span>
      </div>
    </div>
  );
}
