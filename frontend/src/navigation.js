// Sidebar sections in display order. `id` is the view key held in App state;
// the URL deliberately does not change when the view does.
export const NAV_SECTIONS = [
  {
    title: 'Overview',
    items: [{ id: 'dashboard', label: 'Dashboard' }],
  },
  {
    title: 'Waste Monitoring',
    items: [
      { id: 'live-sorting', label: 'Live Sorting' },
      { id: 'smart-bins', label: 'Smart Bins' },
      { id: 'hazard-detection', label: 'Hazard Detection' },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { id: 'waste-analytics', label: 'Waste Analytics' },
      { id: 'ai-insights', label: 'AI Insights / Waste Audit' },
      { id: 'procurement-intelligence', label: 'Procurement Intelligence' },
    ],
  },
  {
    title: 'AI Tools',
    items: [
      { id: 'identify-item', label: 'Identify Item' },
      { id: 'ask-tossiq', label: 'Ask TossIQ / ASKU' },
    ],
  },
  {
    title: 'Management',
    items: [
      { id: 'locations-devices', label: 'Locations & Devices' },
      { id: 'operations-alerts', label: 'Operations & Alerts' },
    ],
  },
  {
    title: 'Reports & Settings',
    items: [
      { id: 'reports', label: 'Reports' },
      { id: 'settings', label: 'Settings' },
    ],
  },
];

// Views a later roadmap stage will build out. The copy is deliberately honest
// about there being nothing there yet.
export const PLACEHOLDER_TEXT = {
  'live-sorting':
    'This section is not yet built. A later stage of the roadmap will add live sorting monitoring here.',
  'smart-bins':
    'This section is not yet built. A later stage of the roadmap will add smart bin monitoring here.',
  'waste-analytics':
    'This section is not yet built. A later stage of the roadmap will add deeper waste analytics here.',
  'procurement-intelligence':
    'This section is not yet built. A later stage of the roadmap will add procurement intelligence here.',
  'ask-tossiq':
    'This section is not yet built. A later stage of the roadmap will add the Ask TossIQ assistant here.',
  'locations-devices':
    'This section is not yet built. A later stage of the roadmap will add locations and device management here.',
  'operations-alerts':
    'This section is not yet built. A later stage of the roadmap will add operations and alerts here.',
  reports: 'This section is not yet built. A later stage of the roadmap will add reports here.',
  settings: 'This section is not yet built. A later stage of the roadmap will add settings here.',
};
