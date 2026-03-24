const API_URL = '';

// State
let token = localStorage.getItem('access_token');
let currentUserRole = '';
let currentLeads = [];

// DOM Elements
const authView = document.getElementById('authView');
const dashboardView = document.getElementById('dashboardView');
const loginForm = document.getElementById('loginForm');
const loginLoader = document.getElementById('loginLoader');
const logoutBtn = document.getElementById('logoutBtn');
const currentUserBadge = document.getElementById('currentUser');
const leadsTableBody = document.getElementById('leadsTableBody');
const createLeadModal = document.getElementById('createLeadModal');
const addLeadBtn = document.getElementById('addLeadBtn');
const closeModalBtn = document.getElementById('closeModalBtn');
const cancelLeadBtn = document.getElementById('cancelLeadBtn');
const createLeadForm = document.getElementById('createLeadForm');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const leadsLoader = document.getElementById('leadsLoader');
const noLeadsState = document.getElementById('noLeadsState');
const adminStatsBar = document.getElementById('adminStatsBar');
const statTotal = document.getElementById('statTotal');
const statConverted = document.getElementById('statConverted');
const statFollow = document.getElementById('statFollow');
const statRate = document.getElementById('statRate');

// New DOM Elements
const editLeadModal = document.getElementById('editLeadModal');
const editLeadForm = document.getElementById('editLeadForm');
const closeEditModalBtn = document.getElementById('closeEditModalBtn');
const cancelEditBtn = document.getElementById('cancelEditBtn');
const editLeadStatus = document.getElementById('editLeadStatus');
const escalationReasonGroup = document.getElementById('escalationReasonGroup');

// Initialize
function init() {
    if (token) {
        showDashboard();
    } else {
        showAuth();
    }
}

// Navigation
function showAuth() {
    authView.classList.remove('hidden');
    dashboardView.classList.add('hidden');
}

function showDashboard() {
    authView.classList.add('hidden');
    dashboardView.classList.remove('hidden');
    fetchCurrentUser().then(() => {
        if (currentUserRole === 'Admin') {
            loadAdminStats();
        } else {
            adminStatsBar.classList.add('hidden');
        }
    });
    loadLeads();
}

function showToast(msg, isError = false) {
    toastMessage.textContent = msg;
    toastMessage.style.color = isError ? "var(--warning)" : "var(--success)";
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

// API Calls
async function fetchCurrentUser() {
    try {
        const res = await fetch(`${API_URL}/users/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            const user = await res.json();
            currentUserBadge.textContent = `${user.username} (${user.role.replace('RoleEnum.', '')})`;
            currentUserRole = user.role;
        } else if (res.status === 401) {
            handleLogout();
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadAdminStats() {
    try {
        const res = await fetch(`${API_URL}/admin/stats`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            const stats = await res.json();
            statTotal.textContent = stats.total_leads;
            statConverted.textContent = stats.converted;
            statFollow.textContent = stats.follow_up_needed;
            statRate.textContent = stats.conversion_rate;
            adminStatsBar.classList.remove('hidden');
        }
    } catch (e) {
        console.error("Failed to load admin stats", e);
    }
}

async function loadLeads() {
    leadsLoader.classList.remove('hidden');
    noLeadsState.classList.add('hidden');
    leadsTableBody.innerHTML = '';
    
    try {
        const res = await fetch(`${API_URL}/leads`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (res.ok) {
            currentLeads = await res.json();
            renderLeads(currentLeads);
        } else {
            showToast("Failed to load leads", true);
        }
    } catch (e) {
        showToast("Network error", true);
    } finally {
        leadsLoader.classList.add('hidden');
    }
}

// Render Logic
function renderLeads(leads) {
    if (!leads.length) {
        noLeadsState.classList.remove('hidden');
        return;
    }
    
    leads.forEach(lead => {
        const tr = document.createElement('tr');
        
        // Clean status formatting
        let displayStatus = lead.status.replace('LeadStatus.', '');
        const statusClass = `status-${displayStatus.replace(' ', '-')}`;
        
        tr.innerHTML = `
            <td>
                <span class="lead-name">${lead.name}</span>
                <span class="lead-subtext">ID: #${lead.id}</span>
            </td>
            <td>
                <span class="lead-name">${lead.email}</span>
                <span class="lead-subtext">${lead.phone}</span>
            </td>
            <td>${lead.source}</td>
            <td><span class="status ${statusClass}">${displayStatus}</span></td>
            <td><span class="lead-subtext">${new Date(lead.created_at).toLocaleDateString()}</span></td>
            <td>
                <button class="btn btn-outline" onclick="openEditModal(${lead.id})" style="padding: 6px 12px; font-size: 13px;">View / Edit</button>
            </td>
        `;
        leadsTableBody.appendChild(tr);
    });
}

// Global modal function
window.openEditModal = (id) => {
    const lead = currentLeads.find(l => l.id === id);
    if (!lead) return;

    document.getElementById('editModalTitle').textContent = `Manage Lead: ${lead.name}`;
    document.getElementById('editLeadId').value = lead.id;
    document.getElementById('editLeadVersion').value = lead.version;
    document.getElementById('editLeadStatus').value = lead.status.replace('LeadStatus.', '');
    
    editLeadModal.classList.remove('hidden');
};

const closeEditModal = () => {
    editLeadModal.classList.add('hidden');
    editLeadForm.reset();
    escalationReasonGroup.style.display = 'none';
};

closeEditModalBtn.addEventListener('click', closeEditModal);
cancelEditBtn.addEventListener('click', closeEditModal);

editLeadStatus.addEventListener('change', (e) => {
    if (e.target.value === 'Escalated') {
        escalationReasonGroup.style.display = 'block';
    } else {
        escalationReasonGroup.style.display = 'none';
    }
});

editLeadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('editLeadId').value;
    const version = parseInt(document.getElementById('editLeadVersion').value);
    
    const updateData = {
        status: document.getElementById('editLeadStatus').value,
        notes: document.getElementById('editLeadNotes').value,
        version: version
    };

    if (updateData.status === 'Escalated') {
        updateData.reason = document.getElementById('escalationReason').value;
    }

    try {
        const res = await fetch(`${API_URL}/leads/${id}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });

        if (res.ok) {
            showToast("Lead updated successfully");
            closeEditModal();
            loadLeads();
        } else {
            const err = await res.json();
            showToast(err.detail || "Update failed", true);
        }
    } catch (e) {
        showToast("Network error", true);
    }
});

// Event Listeners
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginLoader.classList.remove('hidden');
    
    const formData = new URLSearchParams();
    formData.append('username', e.target.username.value);
    formData.append('password', e.target.password.value);
    
    try {
        const res = await fetch(`${API_URL}/token`, {
            method: 'POST',
            body: formData
        });
        
        if (res.ok) {
            const data = await res.json();
            token = data.access_token;
            localStorage.setItem('access_token', token);
            showDashboard();
            loginForm.reset();
            showToast("Successfully logged in");
        } else {
            showToast("Invalid credentials", true);
        }
    } catch (e) {
        showToast("Network error. Is the server running?", true);
    } finally {
        loginLoader.classList.add('hidden');
    }
});

function handleLogout() {
    token = null;
    localStorage.removeItem('access_token');
    showAuth();
}

logoutBtn.addEventListener('click', handleLogout);

// Modal Logic
addLeadBtn.addEventListener('click', () => {
    createLeadModal.classList.remove('hidden');
});

const closeModal = () => {
    createLeadModal.classList.add('hidden');
    createLeadForm.reset();
};

closeModalBtn.addEventListener('click', closeModal);
cancelLeadBtn.addEventListener('click', closeModal);

createLeadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const leadData = {
        name: document.getElementById('leadName').value,
        email: document.getElementById('leadEmail').value,
        phone: document.getElementById('leadPhone').value,
        source: document.getElementById('leadSource').value
    };
    
    try {
        const res = await fetch(`${API_URL}/leads`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(leadData)
        });
        
        if (res.ok) {
            showToast("Lead created successfully");
            closeModal();
            loadLeads();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to create lead", true);
        }
    } catch (e) {
        showToast("Network error", true);
    }
});

// Run Init
init();
