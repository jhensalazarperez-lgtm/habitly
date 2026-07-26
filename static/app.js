const habitListEl = document.getElementById("habit-list");
const emptyStateEl = document.getElementById("empty-state");

const modalNewHabit = document.getElementById("modal-new-habit");
const modalLog = document.getElementById("modal-log");
const modalDetail = document.getElementById("modal-detail");
const modalProfile = document.getElementById("modal-profile");
const modalConfirmDelete = document.getElementById("modal-confirm-delete");

let pendingDeleteHabitId = null;

function openDeleteConfirm(habitId, habitName) {
  pendingDeleteHabitId = habitId;
  document.getElementById("confirm-delete-name").textContent = habitName || "this habit";
  openModal(modalConfirmDelete);
}

document.getElementById("confirm-delete-btn").addEventListener("click", async () => {
  if (!pendingDeleteHabitId) return;
  await fetch(`/api/habits/${pendingDeleteHabitId}`, { method: "DELETE" });
  pendingDeleteHabitId = null;
  closeModal(modalConfirmDelete);
  loadHabits();
  loadSummaryStats();
});

const HABIT_COLORS = ["#723be8", "#d99c3f", "#3f9c8b", "#d85a70", "#4a90d9"];
const THEME_COLORS = ["#723be8", "#d99c3f", "#3f9c8b", "#d85a70", "#4a90d9", "#1a1a1a", "#2f6fa8"];
let selectedTheme = THEME_COLORS[0];
let weeklyChartInstance = null;

// ---------------------------------------------------------------------------
// Modal helpers
// ---------------------------------------------------------------------------

function openModal(modal) {
  modal.classList.add("active");
  document.body.style.overflow = "hidden";
}

function closeModal(modal) {
  modal.classList.remove("active");
  document.body.style.overflow = "";
}

document.querySelectorAll("[data-close-modal]").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(btn.closest(".modal-overlay")));
});

document.querySelectorAll(".modal-overlay").forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal(overlay);
  });
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function applyTheme(color) {
  document.documentElement.style.setProperty("--accent", color);
}

function applyDarkMode(isDark) {
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  try {
    localStorage.setItem("habitly_dark_mode", isDark ? "1" : "0");
  } catch (e) {
    // localStorage can be unavailable (private browsing, etc.) - harmless
    // to skip, the account's real setting still applies after login.
  }
}

function renderThemePicker() {
  const picker = document.getElementById("theme-color-picker");
  picker.innerHTML = "";
  THEME_COLORS.forEach((color) => {
    const swatch = document.createElement("div");
    swatch.className = "color-swatch" + (color === selectedTheme ? " selected" : "");
    swatch.style.backgroundColor = color;
    swatch.addEventListener("click", () => {
      selectedTheme = color;
      document.getElementById("theme-color-input").value = color;
      applyTheme(color); // live preview before saving
      renderThemePicker();
    });
    picker.appendChild(swatch);
  });
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

async function loadProfile() {
  const res = await fetch("/api/profile");
  const profile = await res.json();

  document.getElementById("profile-name").textContent = profile.name;
  document.getElementById("profile-bio").textContent = profile.bio || "";

  const avatarImg = document.getElementById("profile-avatar");
  const avatarPlaceholder = document.getElementById("profile-avatar-placeholder");
  if (profile.avatar_url) {
    avatarImg.src = profile.avatar_url;
    avatarImg.hidden = false;
    avatarPlaceholder.hidden = true;
  } else {
    avatarImg.hidden = true;
    avatarPlaceholder.hidden = false;
    avatarPlaceholder.textContent = profile.name ? profile.name[0].toUpperCase() : "?";
  }

  document.getElementById("profile-name-input").value = profile.name || "";
  document.getElementById("profile-bio-input").value = profile.bio || "";

  selectedTheme = profile.theme_color || THEME_COLORS[0];
  document.getElementById("theme-color-input").value = selectedTheme;
  applyTheme(selectedTheme);
  renderThemePicker();

  document.getElementById("dark-mode-input").checked = !!profile.dark_mode;
  applyDarkMode(!!profile.dark_mode);
}

document.getElementById("edit-profile-btn").addEventListener("click", () => {
  openModal(modalProfile);
});

document.getElementById("dark-mode-input").addEventListener("change", (e) => {
  applyDarkMode(e.target.checked); // live preview before saving
});

document.getElementById("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  await fetch("/api/profile", { method: "POST", body: formData });
  closeModal(modalProfile);
  loadProfile();
});

// ---------------------------------------------------------------------------
// Summary stats bar
// ---------------------------------------------------------------------------

async function loadSummaryStats() {
  const res = await fetch("/api/stats/summary");
  const stats = await res.json();
  document.getElementById("stat-total-habits").textContent = stats.total_habits;
  document.getElementById("stat-best-streak").textContent = stats.best_streak_overall;
  document.getElementById("stat-total-logs").textContent = stats.total_logs_overall;
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Habit list
// ---------------------------------------------------------------------------

async function loadHabits() {
  const res = await fetch("/api/habits");
  const habits = await res.json();

  habitListEl.innerHTML = "";
  emptyStateEl.hidden = habits.length > 0;

  habits.forEach((habit) => {
    const row = document.createElement("div");
    row.className = "habit-row";
    row.style.borderLeftColor = habit.color || HABIT_COLORS[0];

    row.innerHTML = `
      <div class="habit-info" data-open-detail="${habit.id}">
        <p class="habit-name">
          ${escapeHtml(habit.name)}
          ${habit.category ? `<span class="habit-category">${escapeHtml(habit.category)}</span>` : ""}
        </p>
        <p class="habit-status">${habit.logged_today ? "Logged today" : "Not logged today"}</p>
      </div>
      <div class="habit-actions">
        <span class="streak-badge ${habit.streak > 0 ? "active" : ""}" data-open-detail="${habit.id}" title="Click to see this week's days">
          ${habit.streak} day${habit.streak === 1 ? "" : "s"}
        </span>
        <button class="log-today-btn" data-log-habit="${habit.id}" ${habit.logged_today ? "disabled" : ""}>
          ${habit.logged_today ? "Logged" : "Log today"}
        </button>
        <button class="delete-habit-btn" data-delete-habit="${habit.id}" data-habit-name="${escapeHtml(habit.name)}" aria-label="Delete habit">&times;</button>
      </div>
    `;

    habitListEl.appendChild(row);
  });

  document.querySelectorAll("[data-log-habit]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (btn.disabled) return;
      document.getElementById("log-habit-id").value = btn.dataset.logHabit;
      document.getElementById("log-form").reset();
      document.getElementById("photo-preview").hidden = true;
      openModal(modalLog);
    });
  });

  document.querySelectorAll("[data-delete-habit]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openDeleteConfirm(btn.dataset.deleteHabit, btn.dataset.habitName);
    });
  });

  document.querySelectorAll("[data-open-detail]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      openDetail(el.dataset.openDetail);
    });
  });
}

// ---------------------------------------------------------------------------
// New habit form
// ---------------------------------------------------------------------------

document.getElementById("new-habit-btn").addEventListener("click", () => {
  openModal(modalNewHabit);
});

document.getElementById("new-habit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("habit-name").value.trim();
  const category = document.getElementById("habit-category").value.trim();
  if (!name) return;

  await fetch("/api/habits", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, category }),
  });

  e.target.reset();
  closeModal(modalNewHabit);
  loadHabits();
  loadSummaryStats();
});

// ---------------------------------------------------------------------------
// Log today form (with optional photo)
// ---------------------------------------------------------------------------

document.getElementById("log-photo").addEventListener("change", (e) => {
  const file = e.target.files[0];
  const preview = document.getElementById("photo-preview");
  if (!file) {
    preview.hidden = true;
    return;
  }
  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
});

document.getElementById("log-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const habitId = document.getElementById("log-habit-id").value;
  const formData = new FormData(e.target);

  await fetch(`/api/habits/${habitId}/logs`, {
    method: "POST",
    body: formData,
  });

  closeModal(modalLog);
  loadHabits();
  loadSummaryStats();
});

// ---------------------------------------------------------------------------
// Habit detail view (stats + weekly chart + history)
// ---------------------------------------------------------------------------

async function openDetail(habitId) {
  // Open the modal immediately and show a loading state, so the user always
  // sees something even if one of the requests below fails.
  document.getElementById("detail-habit-name").textContent = "Loading...";
  document.getElementById("detail-stats-row").innerHTML = "";
  document.getElementById("detail-logs").innerHTML = "";
  openModal(modalDetail);

  let habit = null;
  try {
    const habitsRes = await fetch("/api/habits");
    const habits = await habitsRes.json();
    habit = habits.find((h) => String(h.id) === String(habitId));
    document.getElementById("detail-habit-name").textContent = habit ? habit.name : "Habit";
  } catch (err) {
    console.error("Failed to load habit info:", err);
    document.getElementById("detail-habit-name").textContent = "Habit";
  }

  try {
    const statsRes = await fetch(`/api/habits/${habitId}/stats`);
    const stats = await statsRes.json();

    document.getElementById("detail-stats-row").innerHTML = `
      <div class="detail-stat">
        <p class="detail-stat-value">${stats.current_streak}</p>
        <p class="detail-stat-label">Current</p>
      </div>
      <div class="detail-stat">
        <p class="detail-stat-value">${stats.best_streak}</p>
        <p class="detail-stat-label">Best</p>
      </div>
      <div class="detail-stat">
        <p class="detail-stat-value">${stats.total_logs}</p>
        <p class="detail-stat-label">Total Logs</p>
      </div>
      <div class="detail-stat">
        <p class="detail-stat-value">${stats.total_minutes}</p>
        <p class="detail-stat-label">Minutes</p>
      </div>
    `;

    try {
      renderWeeklyChart(stats.week, habit ? habit.color : HABIT_COLORS[0]);
    } catch (chartErr) {
      // Chart.js failing to load (e.g. no internet, blocked CDN) should
      // never block the stats/logs below from showing.
      console.error("Chart failed to render:", chartErr);
      document.querySelector(".chart-wrapper").innerHTML =
        '<p class="no-logs">Chart unavailable right now.</p>';
    }
  } catch (err) {
    console.error("Failed to load habit stats:", err);
  }

  try {
    const logsRes = await fetch(`/api/habits/${habitId}/logs`);
    const logs = await logsRes.json();

    const container = document.getElementById("detail-logs");
    container.innerHTML = "";

    if (logs.length === 0) {
      container.innerHTML = `<p class="no-logs">No entries yet — log today to get started.</p>`;
    } else {
      logs.forEach((log) => {
        const entry = document.createElement("div");
        entry.className = "log-entry";
        entry.innerHTML = `
          ${log.photo_url ? `<img src="${log.photo_url}" class="log-entry-photo" alt="Progress photo for ${log.date}">` : ""}
          <div class="log-entry-body">
            <p class="log-entry-date">${log.date}</p>
            ${log.duration_minutes ? `<p class="log-entry-meta">${log.duration_minutes} min</p>` : ""}
            ${log.notes ? `<p class="log-entry-notes">${escapeHtml(log.notes)}</p>` : ""}
          </div>
        `;
        container.appendChild(entry);
      });
    }
  } catch (err) {
    console.error("Failed to load logs:", err);
    document.getElementById("detail-logs").innerHTML =
      '<p class="no-logs">Couldn\'t load history right now.</p>';
  }
}

function renderWeeklyChart(weekData, color) {
  const ctx = document.getElementById("weekly-chart").getContext("2d");
  const labels = weekData.map((d) =>
    new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" })
  );
  const values = weekData.map((d) => (d.logged ? 1 : 0));

  if (weeklyChartInstance) {
    weeklyChartInstance.destroy();
  }

  weeklyChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: color || HABIT_COLORS[0],
          borderRadius: 6,
          maxBarThickness: 28,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        y: { display: false, min: 0, max: 1.2 },
        x: { grid: { display: false } },
      },
    },
  });
}

// ---------------------------------------------------------------------------

loadProfile();
loadSummaryStats();
loadHabits();

// Register the service worker so the app becomes installable and can
// cache static assets for faster/offline loading.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .catch((err) => console.log("Service worker registration failed:", err));
  });
}
