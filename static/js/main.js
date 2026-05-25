// Main JavaScript for fitness platform

document.addEventListener('DOMContentLoaded', () => {
    initCheckinTimer();
});

function initCheckinTimer() {
    const clock = document.getElementById('checkinClock');
    const activeEl = document.getElementById('activeCheckin');
    if (!clock || !activeEl) return;

    // Get start time from data attribute or template variable
    const startTimestamp = window.elapsed || 0;
    if (!startTimestamp) return;

    function update() {
        const diff = Math.floor(Date.now() / 1000) - Math.floor(startTimestamp);
        clock.textContent =
            String(Math.floor(diff / 3600)).padStart(2, '0') + ':' +
            String(Math.floor((diff % 3600) / 60)).padStart(2, '0') + ':' +
            String(diff % 60).padStart(2, '0');
    }

    update();
    setInterval(update, 1000);
}

// Prevent double-tap zoom on buttons
document.addEventListener('touchstart', function() {}, { passive: true });
