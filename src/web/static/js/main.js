// JAIBird Main JavaScript

// Global variables
let loadingModal;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize loading modal
    const loadingModalElement = document.getElementById('loadingModal');
    if (loadingModalElement) {
        loadingModal = new bootstrap.Modal(loadingModalElement);
    }
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});

// Show loading modal with custom text
function showLoading(text = 'Processing...') {
    if (loadingModal) {
        document.getElementById('loadingText').textContent = text;
        loadingModal.show();
    }
}

// Hide loading modal
function hideLoading() {
    if (loadingModal) {
        loadingModal.hide();
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = getOrCreateToastContainer();
    
    const toastElement = document.createElement('div');
    toastElement.className = `toast align-items-center text-white bg-${type} border-0`;
    toastElement.setAttribute('role', 'alert');
    toastElement.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toastElement);
    
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // Remove element after toast is hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// Get or create toast container
function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '1055';
        document.body.appendChild(container);
    }
    return container;
}

// API call wrapper with error handling
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
                ...options.headers
            },
            ...options
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'API call failed');
        }
        
        return data;
    } catch (error) {
        console.error('API call error:', error);
        throw error;
    }
}

// Get CSRF token from meta tag or form
function getCSRFToken() {
    // Try to get from meta tag first
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
        return metaToken.getAttribute('content');
    }
    
    // Try to get from hidden form field
    const hiddenToken = document.querySelector('input[name="csrf_token"]');
    if (hiddenToken) {
        return hiddenToken.value;
    }
    
    return '';
}

// Trigger SENS scraping
async function triggerScrape() {
    showLoading('Scraping SENS announcements...');
    
    try {
        const result = await apiCall('/api/scrape');
        hideLoading();
        
        if (result.status === 'success') {
            showToast(`Successfully scraped ${result.count} new announcements!`, 'success');
            // Refresh page after 2 seconds to show new data
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showToast('Scraping completed but no new announcements found.', 'info');
        }
    } catch (error) {
        hideLoading();
        showToast(`Scraping failed: ${error.message}`, 'danger');
    }
}

// Test notification systems
async function testNotifications() {
    showLoading('Testing notification systems...');
    
    try {
        const result = await apiCall('/api/test_notifications');
        hideLoading();
        
        if (result.status === 'success') {
            let message = 'Notification test results:\n';
            for (const [system, status] of Object.entries(result.results)) {
                const statusText = status === true ? '✅ Working' : 
                                 status === 'disabled' ? '⚠️ Disabled' : '❌ Failed';
                message += `${system.charAt(0).toUpperCase() + system.slice(1)}: ${statusText}\n`;
            }
            
            // Show detailed results in alert
            alert(message);
            showToast('Notification test completed!', 'info');
        } else {
            showToast('Notification test failed!', 'danger');
        }
    } catch (error) {
        hideLoading();
        showToast(`Notification test failed: ${error.message}`, 'danger');
    }
}

// Send daily digest
async function sendDigest() {
    showLoading('Sending daily digest...');
    
    try {
        const result = await apiCall('/api/send_digest');
        hideLoading();
        
        if (result.status === 'success') {
            showToast('Daily digest sent successfully!', 'success');
        } else {
            showToast(`Failed to send digest: ${result.message}`, 'danger');
        }
    } catch (error) {
        hideLoading();
        showToast(`Failed to send digest: ${error.message}`, 'danger');
    }
}

// Update statistics on dashboard
async function updateStats() {
    try {
        const stats = await apiCall('/api/stats', { method: 'GET' });
        
        // Update stat cards if they exist
        updateStatCard('total-sens', stats.sens_announcements?.total || 0);
        updateStatCard('active-companies', stats.companies?.active || 0);
        updateStatCard('urgent-alerts', stats.sens_announcements?.urgent || 0);
        updateStatCard('notifications-sent', stats.notifications?.sent || 0);
        
    } catch (error) {
        console.error('Failed to update stats:', error);
    }
}

// Update individual stat card
function updateStatCard(cardId, value) {
    const card = document.getElementById(cardId);
    if (card) {
        card.textContent = value;
        card.classList.add('fade-in');
    }
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

// Truncate text with ellipsis
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength) + '...';
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success');
    } catch (error) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        showToast('Copied to clipboard!', 'success');
    }
}

// Confirm action with modal
function confirmAction(title, message, confirmCallback, confirmText = 'Confirm') {
    // Create modal if it doesn't exist
    let modal = document.getElementById('confirmModal');
    if (!modal) {
        modal = createConfirmModal();
        document.body.appendChild(modal);
    }
    
    // Update modal content
    modal.querySelector('.modal-title').textContent = title;
    modal.querySelector('.modal-body p').textContent = message;
    modal.querySelector('.btn-danger').textContent = confirmText;
    
    // Set up confirm button click handler
    const confirmBtn = modal.querySelector('.btn-danger');
    confirmBtn.onclick = function() {
        confirmCallback();
        bootstrap.Modal.getInstance(modal).hide();
    };
    
    // Show modal
    new bootstrap.Modal(modal).show();
}

// Create confirm modal dynamically
function createConfirmModal() {
    const modalHTML = `
        <div class="modal fade" id="confirmModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Confirm Action</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>Are you sure you want to proceed?</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger">Confirm</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    const div = document.createElement('div');
    div.innerHTML = modalHTML;
    return div.firstElementChild;
}

// Debounce function for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Auto-refresh page data every 5 minutes
setInterval(function() {
    if (document.visibilityState === 'visible') {
        updateStats();
    }
}, 5 * 60 * 1000);

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        // Page became visible, refresh data
        updateStats();
    }
});
