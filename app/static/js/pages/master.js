// ── Tier dropdowns (auto-submit) ─────────────────────────────────────────────

// core.js's dropdownInit() sets the hidden .dropdown-value on click; this listener
// is registered afterward (core.js loads first, see master_schools.html), so it
// always runs after the value is set and submits the already-updated form.
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.tier-dropdown .dropdown-option').forEach(btn => {
        btn.addEventListener('click', () => btn.closest('form').submit());
    });
});

// ── Default branding color picker ────────────────────────────────────────────

const DEFAULT_COLOR_TOKENS = ['primary', 'secondary', 'tertiary', 'accent'];
const DEFAULT_HEX_RE = /^#[0-9a-fA-F]{6}$/;

function syncDefaultColor(token, value) {
    document.getElementById('default-color-' + token + '-text').value = value;
    document.getElementById('default-color-card-' + token).style.backgroundColor = value;
}

function syncDefaultColorText(token, value) {
    if (DEFAULT_HEX_RE.test(value)) {
        document.getElementById('default-color-' + token).value = value;
        document.getElementById('default-color-card-' + token).style.backgroundColor = value;
    }
}

// ── Branding JSON modal ──────────────────────────────────────────────────────

// data-* attributes (read via .dataset below) rather than passing schoolName
// through an inline onclick="...(...)" attribute -- Jinja's |tojson escapes for
// safe embedding in a <script> block, not inside a double-quoted HTML
// attribute, so a school name containing a `"` (or one Jinja autoescape leaves
// unescaped for tojson's Markup-safe output) would terminate the onclick
// attribute early and silently break the button.
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.branding-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openBrandingModal(btn.dataset.schoolId, btn.dataset.schoolName));
    });
});

function openBrandingModal(schoolId, schoolName) {
    document.getElementById('branding-modal-title').textContent = `Edit branding.json — ${schoolName}`;
    document.getElementById('branding-modal-textarea').value = BRANDING_RAW_BY_SCHOOL[schoolId];
    document.getElementById('branding-modal-form').action = BRANDING_RAW_URL_TEMPLATE.replace('/schools/0/', `/schools/${schoolId}/`);
    document.getElementById('branding-modal-overlay').classList.add('open');
}

function closeBrandingModal() {
    document.getElementById('branding-modal-overlay').classList.remove('open');
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeBrandingModal();
});

async function saveDefaultBranding() {
    const colors = {};
    for (const token of DEFAULT_COLOR_TOKENS) {
        const el = document.getElementById('default-color-' + token + '-text');
        const value = el.value.trim();
        if (!DEFAULT_HEX_RE.test(value)) {
            toast(`Invalid hex color for ${token}: "${value}"`, 'error');
            return;
        }
        colors[token] = value;
    }

    try {
        const response = await fetch('/master/default-branding', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ colors })
        });
        const data = await response.json();
        if (!response.ok) {
            toast(data.error || 'Failed to update default branding.', 'error');
            return;
        }
        toast('Default branding updated successfully.', 'success');
    } catch {
        toast('An error occurred. Please try again.', 'error');
    }
}
