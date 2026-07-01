const authForm = document.querySelector("[data-demo-login]");
const signupForm = document.querySelector("[data-demo-signup]");
const logoutLinks = document.querySelectorAll("[data-logout-link]");
const forgotPasswordForm = document.querySelector("[data-forgot-password-form]");
const THEME_STORAGE_KEY = "eduforge-theme";
const PROJECT_CACHE_KEY = "eduforge-project-cache";
const RECOMMENDATION_DOMAIN_ALIASES = {
  EdTech: "Education"
};
const PINNED_RECOMMENDATION_PROJECTS = {
  Hackathon: ["HackSense AI Evaluator"],
  Education: ["LearnPath AI Recommender"]
};
let currentUserPromise = null;

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = { ok: false, message: "Unexpected server response." };
  }

  if (!response.ok) {
    const failure = new Error(payload.message || "Request failed.");
    failure.status = response.status;
    failure.payload = payload;
    throw failure;
  }

  return payload;
}

function getPageName() {
  const path = window.location.pathname.split("/").pop();
  return path || "index.html";
}

function isAuthPage() {
  const page = getPageName();
  return page === "index.html" || page === "signup.html" || page === "forgot-password.html" || page === "";
}

async function requireCurrentUser() {
  if (currentUserPromise) {
    return currentUserPromise;
  }

  currentUserPromise = (async () => {
    try {
      const payload = await apiFetch("/api/me");
      return payload.user;
    } catch (error) {
      if (error.status === 401 && !isAuthPage()) {
        currentUserPromise = null;
        window.location.href = "index.html";
        return null;
      }
      currentUserPromise = null;
      throw error;
    }
  })();

  try {
    return await currentUserPromise;
  } catch (error) {
    throw error;
  }
}

function uniqueList(values) {
  return [...new Set((values || []).map((value) => String(value).trim()).filter(Boolean))];
}

function bySelector(selector) {
  return document.querySelector(selector);
}

function bySelectorAll(selector) {
  return [...document.querySelectorAll(selector)];
}

function notify(message) {
  window.alert(message);
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function readProjectCache() {
  try {
    return JSON.parse(window.sessionStorage.getItem(PROJECT_CACHE_KEY) || "{}");
  } catch (error) {
    return {};
  }
}

function writeProjectCache(cache) {
  try {
    window.sessionStorage.setItem(PROJECT_CACHE_KEY, JSON.stringify(cache));
  } catch (error) {
  }
}

function cacheProject(project) {
  if (!project || !project.id) return;
  const cache = readProjectCache();
  cache[String(project.id)] = {
    ...(cache[String(project.id)] || {}),
    ...project
  };
  writeProjectCache(cache);
}

function cacheProjects(projects) {
  (projects || []).forEach(cacheProject);
}

function getCachedProject(projectId) {
  if (!projectId) return null;
  const cache = readProjectCache();
  return cache[String(projectId)] || null;
}

function setText(selector, value) {
  const element = bySelector(selector);
  if (element) {
    element.textContent = value;
  }
}

function getStoredTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch (error) {
    return null;
  }
}

function getPreferredTheme() {
  const storedTheme = getStoredTheme();
  if (storedTheme === "dark" || storedTheme === "light") {
    return storedTheme;
  }
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function syncThemeToggleLabel() {
  const button = bySelector("[data-theme-toggle]");
  if (!button) return;
  const activeTheme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const nextActionLabel = activeTheme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  button.textContent = activeTheme === "dark" ? "☀" : "☾";
  button.setAttribute("aria-label", nextActionLabel);
  button.setAttribute("title", nextActionLabel);
}

function applyTheme(theme, persist = true) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (persist) {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    } catch (error) {
    }
  }
  syncThemeToggleLabel();
}

function initThemeToggle() {
  applyTheme(getPreferredTheme(), false);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "theme-toggle";
  button.setAttribute("data-theme-toggle", "true");
  button.addEventListener("click", () => {
    const currentTheme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });

  const dashboardHeader = bySelector(".dashboard-header");
  const headerAction = dashboardHeader?.querySelector(".primary-btn, .secondary-btn, .ghost-link");
  const topNav = bySelector(".top-nav");
  const navAction = topNav?.querySelector(".ghost-link, .primary-btn, .secondary-btn");

  if (headerAction?.parentElement === dashboardHeader) {
    dashboardHeader.insertBefore(button, headerAction);
  } else if (dashboardHeader) {
    dashboardHeader.appendChild(button);
  } else if (navAction?.parentElement === topNav) {
    topNav.insertBefore(button, navAction);
  } else if (topNav) {
    topNav.appendChild(button);
  } else {
    document.body.appendChild(button);
  }

  syncThemeToggleLabel();
}

function renderPills(values, className = "pill-link") {
  const items = uniqueList(values);
  if (!items.length) {
    return `<span class="${className}">Not added yet</span>`;
  }
  return items.map((value) => `<span class="${className}">${value}</span>`).join("");
}

function normalizeRecommendationDomain(domain) {
  const cleaned = String(domain || "").trim();
  return RECOMMENDATION_DOMAIN_ALIASES[cleaned] || cleaned;
}

function renderProjectDetailContent(project, currentUser) {
  return `
    <div class="panel-header">
      <h2>${project.title || "Untitled project"}</h2>
      <span class="muted-badge">Innovation score: ${project.innovation_score ?? "Pending"}</span>
    </div>
    <h3 class="idea-title">${project.owner?.full_name || "Unknown creator"}</h3>
    <p class="muted-text">${project.description || "Project summary coming in."}</p>

    <div class="idea-section">
      <h4>Overview of project</h4>
      <p class="muted-text">${project.description || "Project overview will appear here."}</p>
    </div>
    <div class="idea-section">
      <h4>Required skills</h4>
      <div class="result-links">${renderPills(project.required_skills)}</div>
    </div>
    <div class="idea-section">
      <h4>Languages used</h4>
      <div class="result-links">${renderPills(project.tech_stack)}</div>
    </div>
    <div class="idea-section">
      <h4>Project domain</h4>
      <div class="result-links">${renderPills(project.domain ? [project.domain] : [])}</div>
    </div>
    <div class="idea-section">
      <h4>Project objective</h4>
      <p class="muted-text">${project.objective || "Not added yet"}</p>
    </div>
    <div class="idea-section">
      <h4>Preferred team size</h4>
      <p class="muted-text">${project.team?.length || 0} of ${project.team_size || "?"} members currently on this project.</p>
    </div>
    <div class="idea-section">
      <h4>Target users</h4>
      <p class="muted-text">${project.target_users || "Not added yet"}</p>
    </div>
    <div class="idea-section">
      <h4>Problem statement</h4>
      <p class="muted-text">${project.problem_statement || "Not added yet"}</p>
    </div>
    <div class="idea-section">
      <h4>Key features</h4>
      <div class="result-links">${renderPills(project.key_features)}</div>
    </div>
    <div class="idea-section">
      <h4>Your skill gap</h4>
      <p class="muted-text">${project.viewer_skill_gap?.summary || "Loading your project fit..."}</p>
      <div class="result-links">${renderPills(project.viewer_skill_gap?.missing_skills)}</div>
    </div>
    <div class="idea-section">
      <h4>Creator skill gap</h4>
      <p class="muted-text">${project.creator_skill_gap_summary || "Not added yet"}</p>
      <div class="result-links">${renderPills(project.creator_skill_gap)}</div>
    </div>
    ${project.id
      ? `
          <div class="feed-action-group">
            <button class="secondary-btn" type="button" data-like-project-detail="${project.id}">
              ${project.liked_by_viewer ? "Unlike project" : "Like project"}
            </button>
          </div>
          ${project.is_owner
            ? `
                <div class="feed-action-group">
                  <a class="secondary-btn" href="submit-project.html?project_id=${project.id}">Edit project</a>
                  <button class="secondary-btn" type="button" data-delete-project-owner>Delete project</button>
                </div>
              `
            : project.team?.some((member) => member.id === currentUser?.id)
              ? `<p class="muted-text">You are already part of this team.</p>`
              : project.team_is_full
                ? `<button class="primary-btn" type="button" disabled>Team is full (${project.team_size} members)</button>`
                : project.join_request_status === "pending"
                  ? `<button class="primary-btn" type="button" disabled>Join request pending owner approval</button>`
                  : `<button class="primary-btn" type="button" data-request-join>Request to join team</button>`
          }
        `
      : ""
    }
  `;
}

function renderProjectDetailSidePanels(project) {
  const sidePanels = bySelectorAll(".idea-side-stack .panel");
  if (sidePanels[0]) {
    sidePanels[0].innerHTML = `
      <div class="panel-header">
        <h2>${project.is_owner ? "Pending join requests" : "Suggested collaborators"}</h2>
        <span class="muted-badge">${project.is_owner ? "Owner approval" : "Project fit"}</span>
      </div>
      <div class="insight-list compact-insights">
        ${project.is_owner
          ? project.pending_join_requests?.length
            ? project.pending_join_requests
              .map(
                (request) => `
                    <article>
                      <h3>${request.requester.full_name}</h3>
                      <p>${request.requester.year_role || "Student collaborator"} at ${request.requester.college || "Campus community"}</p>
                      <div class="feed-action-group">
                        <button class="secondary-btn small-btn" type="button" data-handle-request="${request.id}" data-request-action="approve">Approve</button>
                        <button class="secondary-btn small-btn" type="button" data-handle-request="${request.id}" data-request-action="decline">Decline</button>
                      </div>
                    </article>
                  `
              )
              .join("")
            : `<article><p>No pending join requests right now.</p></article>`
          : project.collaborator_suggestions?.length
            ? project.collaborator_suggestions
              .map(
                (person) => `
                    <article>
                      <h3>${person.full_name}</h3>
                      <p>${person.match_reason}</p>
                      <button class="secondary-btn" type="button" data-connect-suggested="${person.id}" ${(person.connection_status === "pending" || person.connection_status === "accepted" || person.connection_status === "incoming_pending") ? "disabled" : ""}>
                        ${getConnectionCta(person.connection_status, person.full_name.split(" ")[0]).label}
                      </button>
                    </article>
                  `
              )
              .join("")
            : `<article><p>No open collaborator suggestions right now.</p></article>`
        }
      </div>
    `;
  }

  if (sidePanels[1]) {
    sidePanels[1].innerHTML = `
      <div class="panel-header">
        <h2>Project team</h2>
        <span class="muted-badge">${project.team?.length || 0}/${project.team_size || "?"} members</span>
      </div>
      <div class="check-list">
        ${(project.team || []).map((member) => `<span class="check-item complete">${member.full_name}</span>`).join("") || '<span class="check-item">Team details loading</span>'}
      </div>
    `;
  }

  if (sidePanels[2]) {
    sidePanels[2].innerHTML = `
      <div class="panel-header">
        <h2>Project links and stats</h2>
        <span class="muted-badge">Relevant details</span>
      </div>
      <div class="idea-timeline">
        <article><strong>Status</strong><p>${project.status || "Idea"}</p></article>
        <article><strong>Views</strong><p>${project.views ?? 0}</p></article>
        <article><strong>Likes</strong><p>${project.likes ?? 0}</p></article>
        <article><strong>GitHub</strong><p>${project.github_url ? `<a class="text-link" href="${project.github_url}" target="_blank" rel="noreferrer">Open repository</a>` : "Not added yet"}</p></article>
        <article><strong>Demo</strong><p>${project.demo_url ? `<a class="text-link" href="${project.demo_url}" target="_blank" rel="noreferrer">Open demo</a>` : "Not added yet"}</p></article>
      </div>
    `;
  }
}

function createChipController(wrapper) {
  if (!wrapper) return null;

  const list = wrapper.querySelector("[data-chip-list]");
  const input = wrapper.querySelector("[data-chip-text]");
  const addButton = wrapper.querySelector("[data-chip-add]");
  const suggestionChips = wrapper.querySelectorAll("[data-chip-option]");

  if (!list || !input || !addButton) {
    return null;
  }

  function syncValidity() {
    if (wrapper.dataset.required === "true" && !list.querySelector(".chip")) {
      const fieldLabel = wrapper.dataset.chipLabel || "this field";
      input.setCustomValidity(`Please add at least one item for ${fieldLabel.toLowerCase()}.`);
      return false;
    }
    input.setCustomValidity("");
    return true;
  }

  function bindChip(chip) {
    chip.setAttribute("role", "button");
    chip.setAttribute("tabindex", "0");
    chip.title = "Click to remove";

    const removeChip = () => {
      if (wrapper.dataset.disabled === "true") return;
      chip.remove();
      syncValidity();
    };

    chip.addEventListener("click", removeChip);
    chip.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        removeChip();
      }
    });
  }

  function addValue(value) {
    if (wrapper.dataset.disabled === "true") return;
    const cleaned = String(value || "").trim();
    if (!cleaned) return;
    const exists = [...list.querySelectorAll(".chip")].some(
      (chip) => chip.textContent.trim().toLowerCase() === cleaned.toLowerCase()
    );
    if (exists) {
      input.value = "";
      syncValidity();
      return;
    }
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = cleaned;
    bindChip(chip);
    list.appendChild(chip);
    input.value = "";
    syncValidity();
  }

  function readValues() {
    return [...list.querySelectorAll(".chip")].map((chip) => chip.textContent.trim()).filter(Boolean);
  }

  function setValues(values) {
    list.innerHTML = "";
    uniqueList(values).forEach(addValue);
    syncValidity();
  }

  addButton.addEventListener("click", () => addValue(input.value));
  input.addEventListener("keydown", (event) => {
    if (wrapper.dataset.disabled === "true") return;
    if (event.key === "Enter") {
      event.preventDefault();
      addValue(input.value);
    }
  });
  input.addEventListener("input", () => {
    input.setCustomValidity("");
  });

  suggestionChips.forEach((chip) => {
    chip.setAttribute("role", "button");
    chip.setAttribute("tabindex", "0");
    chip.title = "Click to add";

    const addSuggested = () => addValue(chip.textContent.trim());
    chip.addEventListener("click", addSuggested);
    chip.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        addSuggested();
      }
    });
  });

  syncValidity();

  return {
    readValues,
    setValues,
    validate: syncValidity,
    setDisabled(disabled) {
      wrapper.dataset.disabled = disabled ? "true" : "false";
      input.disabled = disabled;
      addButton.disabled = disabled;
      suggestionChips.forEach((chip) => {
        chip.setAttribute("aria-disabled", disabled ? "true" : "false");
        chip.style.pointerEvents = disabled ? "none" : "auto";
        chip.style.opacity = disabled ? "0.55" : "1";
      });
      list.querySelectorAll(".chip").forEach((chip) => {
        chip.style.pointerEvents = disabled ? "none" : "auto";
        chip.style.opacity = disabled ? "0.7" : "1";
      });
    }
  };
}

function createChipControllers() {
  const wrappers = bySelectorAll("[data-chip-input]");
  const controllers = new Map();
  wrappers.forEach((wrapper) => {
    const key = wrapper.dataset.field || wrapper.dataset.chipLabel || `chip-${controllers.size}`;
    const controller = createChipController(wrapper);
    if (controller) {
      controllers.set(key, controller);
    }
  });
  return controllers;
}

function setFormControlsDisabled(form, disabled, chipControllers = new Map()) {
  if (!form) return;
  form.querySelectorAll("input, textarea, select").forEach((field) => {
    if (field.id === "profileEmail") {
      field.disabled = true;
      return;
    }
    field.disabled = disabled;
  });
  chipControllers.forEach((controller) => controller.setDisabled(disabled));
}

function findTagFilterValue(selector) {
  const active = bySelector(`${selector}.active`);
  return active ? active.dataset.keyword || active.dataset.feedFilter || active.dataset.teammateFilter || "All" : "All";
}

function getConnectionCta(status, firstName = "Student") {
  if (status === "accepted") {
    return { label: "Connected", disabled: true };
  }
  if (status === "pending") {
    return { label: "Request sent", disabled: true };
  }
  if (status === "incoming_pending") {
    return { label: "Respond in Teammates", disabled: true };
  }
  return { label: `Connect with ${firstName}`, disabled: false };
}

async function handleLogin() {
  if (!authForm) return;

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = authForm.querySelector('input[name="loginEmail"]')?.value?.trim();
    const password = authForm.querySelector('input[name="loginPassword"]')?.value || "";

    try {
      await apiFetch("/api/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      window.location.href = "dashboard.html";
    } catch (error) {
      notify(error.message);
    }
  });
}

async function handleForgotPasswordForm() {
  if (!forgotPasswordForm) return;

  forgotPasswordForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = forgotPasswordForm.querySelector('input[name="resetEmail"]')?.value?.trim() || "";
    const newPassword = forgotPasswordForm.querySelector('input[name="resetPassword"]')?.value || "";
    const confirmPassword = forgotPasswordForm.querySelector('input[name="confirmResetPassword"]')?.value || "";

    if (newPassword !== confirmPassword) {
      notify("Passwords do not match.");
      return;
    }

    try {
      const response = await apiFetch("/api/forgot-password", {
        method: "POST",
        body: JSON.stringify({
          email,
          new_password: newPassword
        })
      });
      notify(response.message || "Password reset successful.");
      window.location.href = `index.html?email=${encodeURIComponent(email)}`;
    } catch (error) {
      notify(error.message);
    }
  });
}

async function handleSignup() {
  if (!signupForm) return;

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const password = signupForm.querySelector('input[name="password"]')?.value || "";
    const confirmPassword = signupForm.querySelector('input[name="confirmPassword"]')?.value || "";
    if (password !== confirmPassword) {
      notify("Passwords do not match.");
      return;
    }

    const payload = {
      full_name: signupForm.querySelector('input[name="fullName"]')?.value?.trim(),
      college: signupForm.querySelector('input[name="college"]')?.value?.trim(),
      email: signupForm.querySelector('input[name="signupEmail"]')?.value?.trim(),
      year_role: signupForm.querySelector('input[name="yearRole"]')?.value?.trim(),
      password,
      interest_tags: signupForm.querySelector('input[name="interestTags"]')?.value || "",
      goals: signupForm.querySelector('textarea[name="buildGoal"]')?.value?.trim()
    };

    try {
      await apiFetch("/api/signup", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      window.location.href = "dashboard.html";
    } catch (error) {
      notify(error.message);
    }
  });
}

function handleLogout() {
  logoutLinks.forEach((link) => {
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await apiFetch("/api/logout", { method: "POST" });
      } catch (error) {
        // Keep logout resilient even if the session is already gone.
      }
      window.location.href = "index.html";
    });
  });
}

async function initProfilePage() {
  const profileForm = bySelector("[data-profile-form]");
  if (!profileForm) return;

  const editButton = bySelector("[data-edit-profile]");
  const saveButton = bySelector("[data-save-profile]");
  const deleteButton = bySelector("[data-delete-profile]");
  const chipControllers = createChipControllers();
  let isEditing = false;

  const profilePayload = await apiFetch("/api/profile");
  const profile = profilePayload.profile;

  bySelector("#profileFullName").value = profile.full_name || "";
  bySelector("#profileEmail").value = profile.email || "";
  bySelector("#profileCollege").value = profile.college || "";
  bySelector("#profileYearRole").value = profile.year_role || "";
  bySelector("#profileBio").value = profile.bio || "";
  bySelector("#profileExperience").value = profile.experience_level || "";
  bySelector("#profileAvailability").value = profile.availability || "";
  bySelector("#profileGithub").value = profile.github_url || "";
  bySelector("#profileLinkedIn").value = profile.linkedin_url || "";
  chipControllers.get("Interested domains")?.setValues(profile.interested_domains);
  chipControllers.get("Skills you have")?.setValues(profile.skills_have);
  chipControllers.get("Skills you want to learn")?.setValues(profile.skills_learn);
  chipControllers.get("Best fit roles")?.setValues([]);

  const setEditingState = (editable) => {
    isEditing = editable;
    setFormControlsDisabled(profileForm, !editable, chipControllers);
    if (saveButton) {
      saveButton.hidden = !editable;
    }
    if (editButton) {
      editButton.textContent = editable ? "Cancel" : "Edit Profile";
    }
  };

  const saveProfile = async () => {
    if (!isEditing) return;
    const payload = {
      full_name: bySelector("#profileFullName").value.trim(),
      college: bySelector("#profileCollege").value.trim(),
      year_role: bySelector("#profileYearRole").value.trim(),
      bio: bySelector("#profileBio").value.trim(),
      experience_level: bySelector("#profileExperience").value,
      availability: bySelector("#profileAvailability").value,
      interested_domains: chipControllers.get("Interested domains")?.readValues() || [],
      skills_have: chipControllers.get("Skills you have")?.readValues() || [],
      skills_learn: chipControllers.get("Skills you want to learn")?.readValues() || [],
      github_url: bySelector("#profileGithub").value.trim(),
      linkedin_url: bySelector("#profileLinkedIn").value.trim(),
      goals: profile.goals || ""
    };

    try {
      const response = await apiFetch("/api/profile", {
        method: "PUT",
        body: JSON.stringify(payload)
      });
      notify(`Profile saved for ${response.profile.full_name}.`);
      syncProfilePreview(response.profile);
      setEditingState(false);
    } catch (error) {
      notify(error.message);
    }
  };

  const syncProfilePreview = (currentProfile) => {
    const initials = (currentProfile.full_name || "NV")
      .split(" ")
      .map((part) => part[0])
      .join("")
      .slice(0, 2)
      .toUpperCase();
    setText(".avatar-circle", initials);
    setText(".profile-hero h3", currentProfile.full_name || "Your name");
    setText(".profile-hero p", currentProfile.bio || "Add a short bio so collaborators understand your interests.");
  };

  syncProfilePreview(profile);
  setEditingState(false);

  if (saveButton) {
    saveButton.addEventListener("click", saveProfile);
  }
  if (editButton) {
    editButton.addEventListener("click", () => {
      if (isEditing) {
        window.location.reload();
        return;
      }
      setEditingState(true);
    });
  }
  if (deleteButton) {
    deleteButton.addEventListener("click", async () => {
      const confirmed = window.confirm("Delete your profile and all your submitted projects?");
      if (!confirmed) return;
      try {
        await apiFetch("/api/profile", { method: "DELETE" });
        notify("Your profile was deleted.");
        window.location.href = "signup.html";
      } catch (error) {
        notify(error.message);
      }
    });
  }
}

async function initDashboardPage() {
  const spotlightPanel = bySelector(".spotlight-panel");
  if (!spotlightPanel) return;

  const payload = await apiFetch("/api/dashboard");
  const { spotlight, trending_projects: trendingProjects, suggested_collaborators: collaborators, stats, user } = payload;
  cacheProjects(trendingProjects);

  if (spotlight) {
    spotlightPanel.innerHTML = `
      <div class="spotlight-copy">
        <span class="card-tag">Innovation Pulse</span>
        <h2>Recommended direction: ${spotlight.title}</h2>
        <p>${spotlight.description}</p>
      </div>
      <div class="spotlight-stats">
        <article>
          <strong>${stats.related_projects}</strong>
          <span>stored projects</span>
        </article>
        <article>
          <strong>${stats.matching_students}</strong>
          <span>suggested collaborators</span>
        </article>
        <article>
          <strong>${spotlight.innovation_score}</strong>
          <span>innovation score</span>
        </article>
      </div>
    `;
  }

  const sidebarCard = bySelector(".sidebar-card");
  if (sidebarCard) {
    sidebarCard.innerHTML = `
      <span class="card-tag">Welcome</span>
      <h3>${user.full_name}</h3>
      <p>Trending projects refresh weekly. Last refresh: ${stats.weekly_trending_refresh}. Next refresh: ${stats.weekly_trending_next_refresh}.</p>
    `;
  }

  const projectList = bySelector(".project-list");
  if (projectList) {
      projectList.innerHTML = trendingProjects
        .map(
          (project) => `
            <a class="project-card project-card-link" href="view-idea.html?project_id=${project.id}">
              <div class="project-card-copy">
                <div class="project-card-topline">
                  <div class="innovation-badge">Innovation score: ${project.innovation_score}</div>
                  <div class="project-domain-pill">${project.domain}</div>
                </div>
                <h3>${project.title}</h3>
                <p>${project.description}</p>
                <div class="project-score-row">
                  <article class="project-score-card">
                    <strong>${project.innovation_score}</strong>
                    <span>innovation score</span>
                  </article>
                  <article class="project-score-card">
                    <strong>${Math.round(project.trending_score || 0)}</strong>
                    <span>trending score</span>
                  </article>
                </div>
              </div>
            </a>
          `
        )
      .join("");
  }

  const collabList = bySelector(".collab-list");
  if (collabList) {
    collabList.innerHTML = collaborators
      .map(
        (person) => `
          <article class="collab-card">
            <h3>${person.full_name}</h3>
            <p>${person.match_reason}</p>
            <button class="secondary-btn" type="button" data-collab-profile="${person.id}">View profile</button>
          </article>
        `
      )
      .join("");

    bySelectorAll("[data-collab-profile]").forEach((button) => {
      button.addEventListener("click", () => {
        window.location.href = "teammates.html";
      });
    });
  }
}

async function initRecommendationsPage() {
  const resultsGrid = bySelector("#resultsGrid");
  if (!resultsGrid) return;

  const searchInput = bySelector("#searchInput");
  const searchButton = bySelector("#runSearch");
  const tagPills = bySelectorAll(".tag-pill");
  const explanationBox = bySelector("#explanationBox");
  const collaboratorResults = bySelector("#collaboratorResults");

  const loadRecommendations = async (domain = "All", search = "") => {
    const effectiveDomain = normalizeRecommendationDomain(domain || "All");
    const [payload, projectPayload] = await Promise.all([
      apiFetch(
        `/api/recommendations?domain=${encodeURIComponent(domain || "All")}&search=${encodeURIComponent(search || "")}`
      ),
      apiFetch(
        `/api/projects?domain=${encodeURIComponent(effectiveDomain || "All")}&search=${encodeURIComponent(search || "")}`
      )
    ]);
    const recommendationBlock = payload.recommendations;
    const items = recommendationBlock.items || [];
    const matchingProjects = projectPayload.projects || [];
    const collaborators = recommendationBlock.collaborators || [];
    cacheProjects(matchingProjects);
    cacheProjects(items.filter((item) => item.project_id).map((item) => ({
      id: item.project_id,
      title: item.title,
      description: item.summary,
      domain: item.domain,
      innovation_score: item.innovation_score
    })));

    const mergedItems = [...items];
    const seenTitles = new Set(mergedItems.map((item) => String(item.title || "").trim().toLowerCase()).filter(Boolean));
    matchingProjects.forEach((project) => {
      const titleKey = String(project.title || "").trim().toLowerCase();
      if (!titleKey || seenTitles.has(titleKey)) return;
      mergedItems.push({
        project_id: project.id,
        title: project.title,
        domain: project.domain,
        summary: project.description,
        match_reason: "Included from stored projects for this domain.",
        innovation_score: project.innovation_score
      });
      seenTitles.add(titleKey);
    });

    const pinnedTitles = PINNED_RECOMMENDATION_PROJECTS[effectiveDomain] || [];
    mergedItems.sort((left, right) => {
      const leftPinned = pinnedTitles.includes(left.title) ? 1 : 0;
      const rightPinned = pinnedTitles.includes(right.title) ? 1 : 0;
      if (leftPinned !== rightPinned) {
        return rightPinned - leftPinned;
      }
      return (Number(right.innovation_score) || 0) - (Number(left.innovation_score) || 0);
    });

    resultsGrid.innerHTML = mergedItems.length
      ? mergedItems
        .map(
          (item) => `
              <article class="result-card">
                <div class="result-meta">
                  <span>${item.domain}</span>
                  <span>Innovation score: ${item.innovation_score}</span>
                </div>
                <div>
                  <h3>${item.title}</h3>
                  <p>${item.summary}</p>
                  <p class="muted-text">${item.match_reason}</p>
                </div>
                <div class="result-links">
                  <span class="pill-link">${recommendationBlock.source === "ollama" ? "Ollama" : "Local fallback"}</span>
                  <span class="pill-link">${effectiveDomain || "All domains"}</span>
                </div>
                <a class="secondary-btn view-idea-btn" href="${item.project_id ? `view-idea.html?project_id=${item.project_id}` : "submit-project.html"}">
                  ${item.project_id ? "View idea" : "Build this idea"}
                </a>
              </article>
            `
        )
        .join("")
      : `
        <article class="result-card">
          <h3>No recommendations yet</h3>
          <p>Try a different domain or submit more projects to improve recommendations.</p>
        </article>
      `;

    if (explanationBox) {
      explanationBox.innerHTML = `
        <article>
          <h3>Recommendation source</h3>
          <p>${recommendationBlock.source === "ollama" ? "Generated with Ollama" : "Local ranking fallback"}</p>
        </article>
        <article>
          <h3>Why these results?</h3>
          <p>${recommendationBlock.explanation}</p>
        </article>
        <article>
          <h3>Domain focus</h3>
          <p>${effectiveDomain || "All"} domain projects are ranked using stored skills, interests, and project insights.</p>
        </article>
        <article>
          <h3>Keyword search</h3>
          <p>${search ? `Results also factor in the keyword "${search}".` : "No extra keyword applied beyond the active domain filter."}</p>
        </article>
      `;
    }

    if (collaboratorResults) {
      collaboratorResults.innerHTML = collaborators.length
        ? collaborators.map((person) => {
          const firstName = (person.full_name || "Student").split(" ")[0];
          const cta = getConnectionCta(person.connection_status, firstName);
          return `
            <article class="collab-card">
              <div class="result-meta">
                <span>${person.year_role || "Student collaborator"}</span>
                <span>${person.college || "Campus community"}</span>
              </div>
              <div>
                <h3>${person.full_name}</h3>
                <p>${person.match_reason}</p>
              </div>
              <div class="result-links">
                ${renderPills(person.interested_domains)}
              </div>
              <div class="feed-action-group">
                <a class="secondary-btn" href="teammates.html">View profile</a>
                <button class="primary-btn" type="button" data-recommend-connect="${person.id}" ${cta.disabled ? "disabled" : ""}>
                  ${cta.label}
                </button>
              </div>
            </article>
          `;
        }).join("")
        : `
          <article class="collab-card">
            <h3>No collaborator matches yet</h3>
            <p>Try another keyword or update your profile skills and interests to improve like-minded people suggestions.</p>
          </article>
        `;

      bySelectorAll("[data-recommend-connect]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await apiFetch("/api/connections", {
              method: "POST",
              body: JSON.stringify({ target_user_id: Number(button.dataset.recommendConnect) })
            });
            notify("Connection request sent.");
            await loadRecommendations(domain, search);
          } catch (error) {
            notify(error.message);
          }
        });
      });
    }
  };

  const runSearch = () => loadRecommendations(findTagFilterValue("[data-keyword]"), searchInput?.value?.trim() || "");

  if (searchButton) {
    searchButton.addEventListener("click", runSearch);
  }
  if (searchInput) {
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runSearch();
      }
    });
  }
  tagPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      tagPills.forEach((tag) => tag.classList.remove("active"));
      pill.classList.add("active");
      if (searchInput) {
        searchInput.value = pill.dataset.keyword || pill.textContent.trim();
      }
      runSearch();
    });
  });

  await loadRecommendations("All", "");
}

async function initSubmitProjectPage() {
  const projectForm = bySelector("[data-project-form]");
  if (!projectForm) return;

  const currentUser = await requireCurrentUser();
  if (!currentUser) return;

  const chipControllers = createChipControllers();
  const publishButton = bySelector("[data-publish-trigger]");
  const managementPanel = bySelector("#projectManagementPanel");
  const teamSizeInput = bySelector("#team_size");
  let editingProjectId = Number(getQueryParam("project_id") || 0);

  const setFormData = (project = null) => {
    bySelector("#projectTitle").value = project?.title || "";
    bySelector("#projectDescription").value = project?.description || "";
    bySelector("#projectDomain").value = project?.domain || "";
    bySelector("#projectStatus").value = project?.status || "";
    if (teamSizeInput) {
      teamSizeInput.value = String(project?.team_size || 2);
    }
    bySelector("#projectGithub").value = project?.github_url || "";
    bySelector("#projectDemo").value = project?.demo_url || "";
    bySelector("#projectObjective").value = project?.objective || "";
    bySelector("#projectTargetUsers").value = project?.target_users || "";
    bySelector("#projectProblemStatement").value = project?.problem_statement || "";
    chipControllers.get("Tech stack")?.setValues(project?.tech_stack || []);
    chipControllers.get("Project tags")?.setValues(project?.tags || []);
    chipControllers.get("Key features")?.setValues(project?.key_features || []);
    publishButton.textContent = project ? "Update project" : "Publish project";
  };

  if (teamSizeInput) {
    teamSizeInput.addEventListener("input", () => {
      const value = Number(teamSizeInput.value);
      if (!Number.isInteger(value) || value < 2 || value > 5) {
        teamSizeInput.setCustomValidity("Team size must be between 2 and 5 members.");
        return;
      }
      teamSizeInput.setCustomValidity("");
    });
  }

  const loadOwnedProjects = async () => {
    const payload = await apiFetch("/api/projects");
    const ownedProjects = payload.projects.filter((project) => project.owner?.id === currentUser.id);

    if (!managementPanel) return;
    managementPanel.innerHTML = ownedProjects.length
      ? ownedProjects
        .map(
          (project) => `
              <article>
                <h3>${project.title}</h3>
                <p>${project.domain} | Team size: ${project.team_size} | Innovation score: ${project.innovation_score}</p>
                <div class="feed-action-group">
                  <button class="secondary-btn small-btn" type="button" data-edit-project="${project.id}">Edit</button>
                  <button class="secondary-btn small-btn" type="button" data-delete-project="${project.id}">Delete</button>
                </div>
              </article>
            `
        )
        .join("")
      : `
        <article>
          <p class="muted-text">Your saved projects will appear here once you publish one.</p>
        </article>
      `;

    bySelectorAll("[data-edit-project]").forEach((button) => {
      button.addEventListener("click", async () => {
        const projectPayload = await apiFetch(`/api/projects/${button.dataset.editProject}`);
        editingProjectId = projectPayload.project.id;
        setFormData(projectPayload.project);
        window.history.replaceState({}, "", `submit-project.html?project_id=${editingProjectId}`);
      });
    });

    bySelectorAll("[data-delete-project]").forEach((button) => {
      button.addEventListener("click", async () => {
        const confirmed = window.confirm("Delete this submitted project?");
        if (!confirmed) return;
        try {
          await apiFetch(`/api/projects/${button.dataset.deleteProject}`, { method: "DELETE" });
          if (Number(button.dataset.deleteProject) === editingProjectId) {
            editingProjectId = 0;
            setFormData(null);
            window.history.replaceState({}, "", "submit-project.html");
          }
          await loadOwnedProjects();
          notify("Project deleted.");
        } catch (error) {
          notify(error.message);
        }
      });
    });
  };

  if (editingProjectId) {
    const projectPayload = await apiFetch(`/api/projects/${editingProjectId}`);
    if (projectPayload.project.owner?.id === currentUser.id) {
      setFormData(projectPayload.project);
    } else {
      editingProjectId = 0;
    }
  } else {
    setFormData(null);
  }

  const submitProject = async () => {
    const controllers = [
      chipControllers.get("Tech stack"),
      chipControllers.get("Project tags"),
      chipControllers.get("Key features")
    ].filter(Boolean);

    if (!projectForm.reportValidity() || controllers.some((controller) => !controller.validate())) {
      notify("Please complete the required project details before publishing.");
      return;
    }

    const payload = {
      title: bySelector("#projectTitle").value.trim(),
      description: bySelector("#projectDescription").value.trim(),
      domain: bySelector("#projectDomain").value,
      status: bySelector("#projectStatus").value,
      team_size: Number(bySelector("#team_size").value),
      tech_stack: chipControllers.get("Tech stack")?.readValues() || [],
      tags: chipControllers.get("Project tags")?.readValues() || [],
      github_url: bySelector("#projectGithub").value.trim(),
      demo_url: bySelector("#projectDemo").value.trim(),
      objective: bySelector("#projectObjective").value.trim(),
      target_users: bySelector("#projectTargetUsers").value.trim(),
      problem_statement: bySelector("#projectProblemStatement").value.trim(),
      key_features: chipControllers.get("Key features")?.readValues() || []
    };

    try {
      const response = await apiFetch(editingProjectId ? `/api/projects/${editingProjectId}` : "/api/projects", {
        method: editingProjectId ? "PUT" : "POST",
        body: JSON.stringify(payload)
      });
      notify(`Project saved with AI-generated innovation score ${response.project.innovation_score}.`);
      editingProjectId = response.project.id;
      cacheProject(response.project);
      window.history.replaceState({}, "", `submit-project.html?project_id=${editingProjectId}`);
      await loadOwnedProjects();
      window.location.href = `view-idea.html?project_id=${response.project.id}`;
    } catch (error) {
      if (error.status === 409 && error.payload?.duplicate) {
        notify(`${error.payload.message}\nClosest match: ${error.payload.project.title}`);
        return;
      }
      notify(error.message);
    }
  };

  if (publishButton) {
    publishButton.addEventListener("click", submitProject);
  }

  await loadOwnedProjects();
}

async function initFeedPage() {
  const feedResults = bySelector("#feedResults");
  if (!feedResults) return;

  const feedSearch = bySelector("#feedSearch");
  const feedSearchButton = bySelector("#feedSearchButton");
  const feedFilterPills = bySelectorAll("[data-feed-filter]");

  const renderFeed = async (domain = "All", search = "") => {
    const trendingPayload = await apiFetch("/api/trending-projects");
    const feedPayload = await apiFetch(
      `/api/projects?domain=${encodeURIComponent(domain)}&search=${encodeURIComponent(search)}`
    );
    cacheProjects(trendingPayload.projects);
    cacheProjects(feedPayload.projects);

    const featured = trendingPayload.projects.slice(0, 2);
    const featuredColumn = bySelector(".featured-column");
    if (featuredColumn) {
      featuredColumn.innerHTML = featured
        .map(
          (project, index) => `
            <article class="featured-feed-card ${index === 1 ? "alt-card" : ""}">
              <div class="result-meta">
                <span>${project.domain}</span>
                <span>Innovation score: ${project.innovation_score}</span>
              </div>
              <h3>${project.title}</h3>
              <p>${project.description}</p>
              <div class="preview-footer">
                <span>${project.views} views</span>
                <span>${project.likes} likes</span>
              </div>
              <a class="secondary-btn view-idea-btn" href="view-idea.html?project_id=${project.id}">View idea</a>
            </article>
          `
        )
        .join("");
    }

    const items = feedPayload.projects;
    feedResults.innerHTML = items.length
      ? items
        .map(
          (project) => `
              <article class="feed-card">
                <div class="feed-card-header">
                  <div>
                    <h3>${project.title}</h3>
                    <p>By ${project.owner?.full_name || "Unknown"} in ${project.domain}</p>
                  </div>
                  <span class="muted-badge">Innovation score: ${project.innovation_score}</span>
                </div>
                <p>${project.description}</p>
                <div class="metric-row">
                  ${project.tags.map((tag) => `<span class="metric-pill">${tag}</span>`).join("")}
                </div>
                <div class="feed-actions">
                  <div class="preview-footer">
                    <span>${project.views} views</span>
                    <span>${project.likes} likes</span>
                  </div>
                  <div class="feed-action-group">
                    <a class="secondary-btn view-idea-btn" href="view-idea.html?project_id=${project.id}">View idea</a>
                    <button class="secondary-btn" type="button" data-like-project="${project.id}">
                      ${project.liked_by_viewer ? "Unlike" : "Like"}
                    </button>
                  </div>
                </div>
              </article>
            `
        )
        .join("")
      : `
        <article class="feed-card">
          <h3>No matching projects</h3>
          <p>Try another search or domain filter.</p>
        </article>
      `;

    bySelectorAll("[data-like-project]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await apiFetch(`/api/projects/${button.dataset.likeProject}/like`, { method: "POST" });
          await renderFeed(domain, search);
        } catch (error) {
          notify(error.message);
        }
      });
    });
  };

  const triggerRender = () => renderFeed(findTagFilterValue("[data-feed-filter]"), feedSearch?.value?.trim() || "");
  if (feedSearchButton) {
    feedSearchButton.addEventListener("click", triggerRender);
  }
  if (feedSearch) {
    feedSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        triggerRender();
      }
    });
  }
  feedFilterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      feedFilterPills.forEach((item) => item.classList.remove("active"));
      pill.classList.add("active");
      triggerRender();
    });
  });

  await renderFeed("All", "");
}

async function initTeammatesPage() {

  const teammateResults =
    document.querySelector("#teammateResults");

  const teammateProfile =
    document.querySelector("#teammateProfile");

  if (!teammateResults || !teammateProfile) return;

  const searchInput =
    document.querySelector("#teammateSearch");

  const searchButton =
    document.querySelector("#teammateSearchButton");

  const filterPills =
    document.querySelectorAll("[data-teammate-filter]");

  const projectTeamSection =
    document.querySelector("#projectTeamSection");

  const projectTeamPanel =
    document.querySelector("#projectTeamPanel");

  const teammateResultsTitle =
    document.querySelector("#teammateResultsTitle");

  const teammateResultsBadge =
    document.querySelector("#teammateResultsBadge");

  const projectTeamBadge =
    document.querySelector("#projectTeamBadge");

  const projectId =
    Number(getQueryParam("project_id") || 0);

  let activeCollaborator = null;
  let activeProject = null;

  const renderProfile = (person) => {

    if (!person) {

      teammateProfile.innerHTML =
        `<div class="teammate-profile-card">
           <p class="muted-text">
             No collaborator selected yet.
           </p>
         </div>`;

      return;
    }

    const initials =
      person.full_name
        .split(" ")
        .map(p => p[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();

    teammateProfile.innerHTML = `
      <div class="teammate-profile-card">

        <div class="profile-hero teammate-hero">

          <div class="avatar-circle">
            ${initials}
          </div>

          <div>
            <h3>${person.full_name}</h3>

            <p>
              ${person.year_role || "Student builder"}
              at ${person.college || "Campus community"}
            </p>

          </div>

        </div>

        <div class="preview-section">
          <h4>About</h4>
          <p class="muted-text">
            ${person.bio || "No bio added yet."}
          </p>
        </div>

        <div class="preview-section">
          <h4>Interested domains</h4>
          <div class="result-links">
            ${renderPills(person.interested_domains)}
          </div>
        </div>

        <div class="preview-section">
          <h4>Skills</h4>
          <div class="result-links">
            ${renderPills(person.skills_have)}
          </div>
        </div>

        <button
          class="primary-btn teammate-action-btn"
          type="button"
          data-connect-profile="${person.id}"

          ${person.connection_status === "pending" ||
        person.connection_status === "accepted" ||
        person.connection_status === "incoming_pending"
        ? "disabled"
        : ""
      }>
          ${getConnectionCta(person.connection_status, person.full_name.split(" ")[0]).label}
        </button>
      </div>
    `;

    document
      .querySelector("[data-connect-profile]")
      ?.addEventListener("click", async () => {
        try {
          await apiFetch(
            "/api/connections",
            {
              method: "POST",
              body: JSON.stringify({
                target_user_id: person.id
              })
            }
          );

          notify(
            `Connection request sent to ${person.full_name}.`
          );

          person.connection_status = "pending";
          renderProfile(person);
          await loadCollaborators();
        } catch (error) {
          notify(error.message);
        }
      });
  };

  const renderProjectTeam = (project) => {
    if (!projectTeamSection || !projectTeamPanel) return;
    if (!project) {
      projectTeamSection.hidden = true;
      return;
    }

    projectTeamSection.hidden = false;
    if (projectTeamBadge) {
      projectTeamBadge.textContent =
        `${project.team.length}/${project.team_size} members`;
    }
    projectTeamPanel.innerHTML =
      project.team.length
        ? project.team.map(member => `
            <article>
              <h3>${member.full_name}</h3>
              <p>${member.year_role || "Project teammate"} at ${member.college || "Campus community"}</p>
              <div class="result-links">
                ${renderPills(member.skills_have)}
              </div>
            </article>
          `).join("")
        : `
          <article>
            <p class="muted-text">No team members have joined this project yet.</p>
          </article>
        `;
  };

  const loadProjectContext = async () => {
    if (!projectId) {
      renderProjectTeam(null);
      return;
    }

    const projectPayload = await apiFetch(`/api/projects/${projectId}`);
    activeProject = projectPayload.project;
    renderProjectTeam(activeProject);

    if (teammateResultsTitle) {
      teammateResultsTitle.textContent =
        `Suggested connections for ${activeProject.title}`;
    }

    if (teammateResultsBadge) {
      teammateResultsBadge.textContent =
        "Project-fit connections";
    }

    setText(
      ".dashboard-header h1",
      "Project Connections"
    );

    setText(
      ".dashboard-header .eyebrow",
      "Find connections for this team"
    );

  };

  const loadCollaborators = async () => {
    const domain =
      findTagFilterValue(
        "[data-teammate-filter]"
      );
    const search = searchInput?.value?.trim() || "";
    const payload = await apiFetch(
        `/api/collaborators?domain=${encodeURIComponent(domain)}&search=${encodeURIComponent(search)}&project_id=${encodeURIComponent(projectId || "")}`
      );

    const items = payload.collaborators;

    activeCollaborator = items.find(i => i.id === activeCollaborator?.id) || items[0] || null;

    teammateResults.innerHTML = items.length ? items.map(person => {
          return `
              <article
                class="teammate-card
                ${activeCollaborator?.id === person.id
              ? "active"
              : ""
            }"
                data-person-id="${person.id}">

                <div class="teammate-card-header">

                  <div>
                    <h3>
                      ${person.full_name}
                    </h3>

                    <p>
                      ${person.year_role ||
            "Student collaborator"
            }
                    </p>

                  </div>

                  <span class="muted-badge">
                    ${person.availability ||
            "Availability not set"
            }
                  </span>

                </div>

                <p>
                  ${person.match_reason}
                </p>

                <p class="muted-text teammate-type-label">
                  ${projectId ? "Connection suggestion for this project" : "General connection suggestion"}
                </p>

                <div class="result-links">
                  ${renderPills(
              person.interested_domains
            )}
                </div>

                <div class="feed-action-group">

                  <button
                    class="secondary-btn small-btn"
                    type="button"
                    data-connect-card="${person.id}"

                    ${person.connection_status ===
              "pending" ||
              person.connection_status ===
              "accepted" ||
              person.connection_status ===
              "incoming_pending"
              ? "disabled"
              : ""
            }>
                    ${getConnectionCta(person.connection_status, person.full_name.split(" ")[0]).label}
                  </button>
                </div>
              </article>
            `;
        }).join("")
        : `
          <article class="teammate-card">
            <h3>No connection suggestions found</h3>
            <p>
              Try a broader search or change
              the domain filter.
            </p>
          </article>
        `;

    document
      .querySelectorAll("[data-person-id]")
      .forEach(card => {

        card.addEventListener("click", () => {
          activeCollaborator =
            items.find(
              i =>
                String(i.id) ===
                card.dataset.personId
            ) || null;

          renderProfile(activeCollaborator);

          document
            .querySelectorAll("[data-person-id]")
            .forEach(node =>
              node.classList.remove(
                "active"
              )
            );

          card.classList.add("active");
        });
      });

    document
      .querySelectorAll(
        "[data-connect-card]"
      )
      .forEach(button => {

        button.addEventListener(
          "click",
          async event => {
            event.stopPropagation();
            try {
              await apiFetch(
                "/api/connections",
                {
                  method: "POST",
                  body: JSON.stringify({
                    target_user_id:
                      Number(
                        button.dataset
                          .connectCard
                      )
                  })
                }
              );

              notify(
                "Connection request sent."
              );

              await loadCollaborators();
            } catch (error) {
              notify(
                error.message
              );
            }
          }
        );
      });

    renderProfile(activeCollaborator);
  };

  if (searchButton)
    searchButton.addEventListener(
      "click",
      loadCollaborators
    );

  if (searchInput)
    searchInput.addEventListener(
      "keydown",
      e => {
        if (e.key === "Enter") {

          e.preventDefault();

          loadCollaborators();
        }

      }
    );

  filterPills.forEach(pill => {

    pill.addEventListener(
      "click",
      () => {

        filterPills.forEach(p =>
          p.classList.remove(
            "active"
          )
        );

        pill.classList.add(
          "active"
        );

        loadCollaborators();

      }
    );

  });
  await loadProjectContext();
  await loadCollaborators();
}

async function initProjectDetailPage() {
  const mainCard = bySelector(".idea-main-card");
  if (!mainCard) return;

  let projectId = getQueryParam("project_id");
  if (!projectId) {
    const projectsPayload = await apiFetch("/api/projects");
    cacheProjects(projectsPayload.projects);
    projectId = projectsPayload.projects[0]?.id;
  }
  if (!projectId) {
    mainCard.innerHTML = `<div class="panel-header"><h2>No projects found</h2></div><p class="muted-text">Submit a project to start building your feed.</p>`;
    return;
  }

  const currentUserPromise = requireCurrentUser();
  const cachedProject = getCachedProject(projectId);
  if (cachedProject) {
    setText(".dashboard-header h1", cachedProject.title || "View Idea");
    const headerLink = bySelector(".dashboard-header .primary-btn");
    if (headerLink) {
      headerLink.textContent = cachedProject.is_owner ? "Edit project" : "Find teammates";
      headerLink.href = cachedProject.is_owner ? `submit-project.html?project_id=${cachedProject.id}` : `teammates.html?project_id=${cachedProject.id || projectId}`;
    }
    mainCard.innerHTML = renderProjectDetailContent(cachedProject, null);
    renderProjectDetailSidePanels(cachedProject);
  }

  const currentUser = await currentUserPromise;
  if (!currentUser) return;

  const renderProject = async () => {
    const payload = await apiFetch(`/api/projects/${projectId}`);
    const project = payload.project;
    cacheProject(project);

    setText(".dashboard-header h1", project.title);
    const headerLink = bySelector(".dashboard-header .primary-btn");
    if (headerLink) {
      headerLink.textContent = project.is_owner ? "Edit project" : "Find teammates";
      headerLink.href = project.is_owner ? `submit-project.html?project_id=${project.id}` : `teammates.html?project_id=${project.id}`;
    }

    mainCard.innerHTML = renderProjectDetailContent(project, currentUser);
    renderProjectDetailSidePanels(project);

    bySelector("[data-request-join]")?.addEventListener("click", async () => {
      try {
        await apiFetch(`/api/projects/${project.id}/join-request`, { method: "POST", body: JSON.stringify({}) });
        notify("Join request sent to the project owner.");
        renderProject();
      } catch (error) {
        notify(error.message);
      }
    });

    bySelector("[data-like-project-detail]")?.addEventListener("click", async () => {
      try {
        await apiFetch(`/api/projects/${project.id}/like`, { method: "POST" });
        renderProject();
      } catch (error) {
        notify(error.message);
      }
    });

    bySelector("[data-delete-project-owner]")?.addEventListener("click", async () => {
      const confirmed = window.confirm("Delete this project?");
      if (!confirmed) return;
      try {
        await apiFetch(`/api/projects/${project.id}`, { method: "DELETE" });
        notify("Project deleted.");
        window.location.href = "feed.html";
      } catch (error) {
        notify(error.message);
      }
    });

    bySelectorAll("[data-handle-request]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await apiFetch(`/api/projects/${project.id}/join-requests/${Number(button.dataset.handleRequest)}`, {
            method: "POST",
            body: JSON.stringify({ action: button.dataset.requestAction })
          });
          notify(`Join request ${button.dataset.requestAction}d.`);
          renderProject();
        } catch (error) {
          notify(error.message);
        }
      });
    });

    bySelectorAll("[data-connect-suggested]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await apiFetch("/api/connections", {
            method: "POST",
            body: JSON.stringify({ target_user_id: Number(button.dataset.connectSuggested) })
          });
          notify("Connection request sent.");
          renderProject();
        } catch (error) {
          notify(error.message);
        }
      });
    });
  };
  await renderProject();
}

async function loadPendingRequests() {
  try {
    const res =
      await apiFetch("/api/pending-requests");
    const container =
      document.getElementById("pendingRequests");
    if (!container) return;
    container.innerHTML = "";
    res.requests.forEach(user => {
      container.innerHTML += `
                <div class="request-card">
                    <h3>${user.full_name}</h3>
                    <p>${user.year_role}</p>
                    <button class="primary-btn small-btn"
                        onclick="acceptConnection(${user.id})">
                        Accept
                    </button>
                    <button class="secondary-btn small-btn"
                        onclick="rejectConnection(${user.id})">
                        Reject
                    </button>
                </div>
            `;
    });

  } catch (error) {console.error(error);
  }
}

async function bootstrap() {
  initThemeToggle();
  handleLogout();
  await handleLogin();
  await handleForgotPasswordForm();
  await handleSignup();

  const pageName = getPageName();
  const protectedPages = new Set([
    "dashboard.html",
    "profile.html",
    "submit-project.html",
    "recommendations.html",
    "feed.html",
    "teammates.html",
    "view-idea.html"
  ]);

  try {
    if (protectedPages.has(pageName) && pageName !== "view-idea.html") {
      const currentUser = await requireCurrentUser();
      if (!currentUser) {
        return;
      }
    }
    if (pageName === "dashboard.html") {
      await initDashboardPage();
    }
    if (pageName === "profile.html") {
      await initProfilePage();
    }
    if (pageName === "submit-project.html") {
      await initSubmitProjectPage();
    }
    if (pageName === "recommendations.html") {
      await initRecommendationsPage();
    }
    if (pageName === "feed.html") {
      await initFeedPage();
    }
    if (pageName === "teammates.html") {
      await initTeammatesPage();
    }
    if (pageName === "view-idea.html") {
      await initProjectDetailPage();
    }
    if (isAuthPage()) {
      try {
        const currentUser = await requireCurrentUser();
        if (currentUser) {
          window.location.href = "dashboard.html";
        }
      } catch (error) {
        // Staying on the auth page is fine if the user is logged out.
      }
    }
  } catch (error) {
    if (error.status !== 401) {
      notify(error.message || "Something went wrong while loading the page.");
    }
  }
}

async function acceptConnection(userId) {
  try {
    console.log("Accepting:", userId);
    await apiFetch(
      "/api/accept-connection",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          requester_id: Number(userId)
        })
      }
    );

    notify("Connection accepted");
    loadPendingRequests();

  } catch (error) {
    console.error(error);
    notify(error.message);
  }
}

async function rejectConnection(userId) {
  try {
    console.log("Rejecting:", userId);
    await apiFetch(
      "/api/reject-connection",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          requester_id: Number(userId)
        })
      }
    );

    notify("Connection rejected");
    loadPendingRequests();

  } catch (error) {
    console.error(error);
    notify(error.message);
  }
}

async function loadConnections() {
  try {
    const res =
      await apiFetch("/api/connections");
    console.log("Connections:", res);
    const container =
      document.getElementById("connectionsList");
    if (!container) return;
    container.innerHTML = "";
    if (!res.connections.length) {
      container.innerHTML =
        "<p>No connections yet</p>";
      return;
    }

    res.connections.forEach(user => {
      container.innerHTML += `
        <div class="connection-card">
            <h3>
                ${user.full_name}
            </h3>

            <p>
                ${user.year_role}
            </p>

            <div class="tag-row">
                ${user.interested_domains
          .map(d =>
            `<span class="tag-pill">${d}</span>`
          ).join("")}

            </div>
            <button
                class="secondary-btn small-btn"
                onclick="removeConnection(${user.id})">
                Remove
            </button>
        </div>
    `;
    });

  } catch (error) {
    console.error(error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadPendingRequests();
  loadConnections();
});

async function removeConnection(userId) {
  try {
    console.log("Removing connection:", userId);
    const res = await apiFetch(
      "/api/remove-connection",
      {
        method: "POST",
        body: JSON.stringify({
          user_id: Number(userId)
        })
      }
    );

    notify(res.message);
    loadConnections();
  } catch (error) {
    console.error(error);
    notify(error.message);
  }
}

bootstrap();
loadPendingRequests();
