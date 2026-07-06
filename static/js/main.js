// main.js - Media Monitoring OJK Jabar

function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("collapsed");
  document.getElementById("mainWrapper").classList.toggle("expanded");
}

function runCrawler() {
  const modal = new bootstrap.Modal(document.getElementById("crawlerModal"));
  modal.show();
  fetch("/api/crawler/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })
    .then(r => r.json())
    .then(data => {
      document.getElementById("crawlerModalBody").innerHTML = data.success
        ? `<div class="text-center py-3"><i class="bi bi-check-circle-fill text-success" style="font-size:2.5rem"></i><p class="mt-3 fw-semibold" style="color:#10b981">Crawling Selesai!</p><p style="color:#94a3b8">${data.message}</p></div>`
        : `<div class="text-center py-3"><i class="bi bi-x-circle-fill text-danger" style="font-size:2.5rem"></i><p class="mt-3" style="color:#ef4444">${data.message}</p></div>`;
      document.getElementById("crawlerModalFooter").style.display = "flex";
    })
    .catch(e => {
      document.getElementById("crawlerModalBody").innerHTML = `<div class="text-center py-3"><p style="color:#ef4444">Error: ${e.message}</p></div>`;
      document.getElementById("crawlerModalFooter").style.display = "flex";
    });
}

// Update clock
function updateClock() {
  const el = document.getElementById("currentDateTime");
  if (el) {
    const now = new Date();
    el.textContent = now.toLocaleDateString("id-ID", { day:"2-digit", month:"short", year:"numeric" }) + ", " +
      now.toLocaleTimeString("id-ID", { hour:"2-digit", minute:"2-digit" }) + " WIB";
  }
}
setInterval(updateClock, 60000);
