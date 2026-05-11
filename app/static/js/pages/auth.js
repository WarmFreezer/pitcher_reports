// School picker dropdown
function dropdownInit() {
    const picker = document.querySelector('.school-picker');
    const trigger = document.getElementById('school-trigger');
    const hidden = document.getElementById('school-value');
    const options = document.querySelectorAll('.school-option');

    if (!picker || !trigger || !hidden || options.length === 0) return;

    trigger.addEventListener('click', () => picker.classList.toggle('open'));

    options.forEach(btn => {
        btn.addEventListener('click', () => {
            const name = btn.dataset.school;
            hidden.value = name;
            trigger.textContent = `${name} ▼`;
            picker.classList.remove('open');
        });
    });

    // Close the dropdown when the user clicks anywhere outside it
    document.addEventListener('click', (e) => {
        if (!picker.contains(e.target)) picker.classList.remove('open');
    });
}
