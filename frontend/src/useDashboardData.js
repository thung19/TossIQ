import { useCallback, useEffect, useState } from 'react';
import { fetchJSON } from './api.js';

const REFRESH_MS = 5000;

/**
 * Loads every dashboard dataset and keeps it fresh on the same 5-second poll
 * the pre-React dashboard used. All requests in a cycle go out in parallel, and
 * one failing request leaves the others' data intact.
 */
export default function useDashboardData(days) {
  const [overview, setOverview] = useState(null);
  const [items, setItems] = useState([]);
  const [locations, setLocations] = useState([]);
  const [products, setProducts] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [events, setEvents] = useState([]);
  const [hazards, setHazards] = useState([]);

  const refreshOverview = useCallback(
    () => fetchJSON(`/stats/overview?days=${days}`).then(setOverview),
    [days],
  );
  const refreshItems = useCallback(
    () => fetchJSON(`/stats/items?days=${days}`).then(setItems),
    [days],
  );
  const refreshLocations = useCallback(
    () => fetchJSON(`/stats/locations?days=${days}`).then(setLocations),
    [days],
  );
  const refreshProducts = useCallback(() => fetchJSON('/products').then(setProducts), []);
  const refreshRecommendations = useCallback(
    () => fetchJSON('/recommendations').then(setRecommendations),
    [],
  );
  const refreshEvents = useCallback(
    () => fetchJSON('/events/recent?limit=20').then(setEvents),
    [],
  );
  const refreshHazards = useCallback(() => fetchJSON('/hazards?days=30').then(setHazards), []);

  const refreshAll = useCallback(
    () =>
      Promise.all([
        refreshOverview(),
        refreshItems(),
        refreshLocations(),
        refreshProducts(),
        refreshRecommendations(),
        refreshEvents(),
        refreshHazards(),
      ]).catch((err) => console.error(err)),
    [
      refreshOverview,
      refreshItems,
      refreshLocations,
      refreshProducts,
      refreshRecommendations,
      refreshEvents,
      refreshHazards,
    ],
  );

  useEffect(() => {
    refreshAll();
    const timer = setInterval(refreshAll, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refreshAll]);

  return {
    overview,
    items,
    locations,
    products,
    recommendations,
    events,
    hazards,
    refreshProducts,
    refreshRecommendations,
    refreshHazards,
  };
}
