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
