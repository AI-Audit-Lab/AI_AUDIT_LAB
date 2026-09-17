document.addEventListener("DOMContentLoaded", () => {
    fetchSummary();
    setInterval(fetchSummary, 15000); // refresh every 15s
});

async function fetchSummary() {
    try {
        const response = await fetch("/api/v1/summary");
        if (!response.ok) throw new Error("API request failed");
        
        const data = await response.json();
        updateUI(data);
    } catch (err) {
        console.error("Error fetching summary:", err);
        const pill = document.getElementById("db-status-pill");
        if (pill) {
            pill.className = "status-pill error";
            pill.innerHTML = `<span class="status-dot" style="background:#ef4444;box-shadow:0 0 8px #ef4444;"></span> Disconnected`;
        }
    }
}

function updateUI(data) {
    // 1. DB Status
    const dbStatus = data.db_status || {};
    const pill = document.getElementById("db-status-pill");
    if (pill) {
        if (dbStatus.connected) {
            pill.innerHTML = `<span class="status-dot"></span> SQLite: ${dbStatus.status}`;
        } else {
            pill.className = "status-pill error";
            pill.innerHTML = `<span class="status-dot" style="background:#ef4444;box-shadow:0 0 8px #ef4444;"></span> ${dbStatus.status}`;
        }
    }

    // 2. Metrics
    const metrics = data.metrics || {};
    
    // Members
    const activeMembers = (metrics.members && metrics.members.ACTIVE) ? metrics.members.ACTIVE : 0;
    const totalMembers = Object.values(metrics.members || {}).reduce((a, b) => a + b, 0);
    document.getElementById("total-members-val").textContent = totalMembers;
    document.getElementById("active-members-sub").textContent = `Active: ${activeMembers}`;

    // Deposits
    const depositTotal = metrics.deposits ? metrics.deposits.total_balance : 0;
    document.getElementById("total-deposits-val").textContent = formatTHB(depositTotal);
    document.getElementById("deposit-accounts-sub").textContent = `Accounts: ${metrics.deposits ? metrics.deposits.total_accounts : 0}`;

    // Loans
    const loanOutstanding = metrics.loans ? metrics.loans.total_outstanding : 0;
    document.getElementById("total-loans-val").textContent = formatTHB(loanOutstanding);
    document.getElementById("loan-principal-sub").textContent = `Principal: ${formatTHB(metrics.loans ? metrics.loans.total_principal : 0)}`;

    // GL Issues
    const glIssues = data.audit_summary.reconciliation.gl_daily_issues_count || 0;
    document.getElementById("gl-issues-val").textContent = glIssues;

    // Anomaly Alerts
    const anom = data.audit_summary.anomaly || {};
    document.getElementById("off-hours-val").textContent = anom.off_hours_transactions_count || 0;
    document.getElementById("outliers-val").textContent = anom.statistical_outliers_count || 0;
    document.getElementById("inactive-txs-val").textContent = anom.inactive_transactions_count || 0;
    document.getElementById("duplicate-refs-val").textContent = anom.duplicate_references_count || 0;
}

function formatTHB(num) {
    return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(num);
}
