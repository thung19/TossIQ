import { NAV_SECTIONS } from '../navigation.js';

export default function Sidebar({ activeView, onNavigate, open }) {
  return (
    <nav className={`sidebar${open ? ' open' : ''}`}>
      <div className="sidebar-brand">TossIQ</div>
      {NAV_SECTIONS.map((section) => (
        <div className="nav-section" key={section.title}>
          <h2 className="nav-section-title">{section.title}</h2>
          {section.items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item${activeView === item.id ? ' active' : ''}`}
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}
