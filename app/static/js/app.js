document.addEventListener("DOMContentLoaded", () => {
    fetchSummary();
    runFastInOutAudit();
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

function syncResultsLink() {
    const largeInMin = parseFloat(document.getElementById("large-in-min")?.value || "500000");
    const outflowRatioMin = parseFloat(document.getElementById("outflow-ratio-min")?.value || "0.80");
    const windowDays = parseInt(document.getElementById("window-days")?.value || "3", 10);

    const resultsLink = document.getElementById("fio-view-results-link");
    if (resultsLink) {
        resultsLink.href = `/fast-in-out-results?large_in_min=${largeInMin}&outflow_ratio_min=${outflowRatioMin}&window_days=${windowDays}`;
    }
}

function applyDashboardPreset(largeIn, ratio, days) {
    const inEl = document.getElementById("large-in-min");
    const ratioEl = document.getElementById("outflow-ratio-min");
    const daysEl = document.getElementById("window-days");
    if (inEl) inEl.value = largeIn;
    if (ratioEl) ratioEl.value = ratio;
    if (daysEl) daysEl.value = days;
    syncResultsLink();
    runFastInOutAudit();
}

async function runFastInOutAudit() {
    syncResultsLink();

    const largeInMin = parseFloat(document.getElementById("large-in-min")?.value || "500000");
    const outflowRatioMin = parseFloat(document.getElementById("outflow-ratio-min")?.value || "0.80");
    const windowDays = parseInt(document.getElementById("window-days")?.value || "3", 10);

    const errBox = document.getElementById("fio-error-alert");
    if (errBox) {
        errBox.style.display = "none";
        errBox.innerHTML = "";
    }

    // Client-side quick check
    const clientErrors = [];
    if (isNaN(largeInMin) || largeInMin <= 0) {
        clientErrors.push("ยอดเงินเข้าขั้นต่ำ (large_in_min) ต้องเป็นตัวเลขที่มากกว่า 0");
    }
    if (isNaN(outflowRatioMin) || outflowRatioMin <= 0 || outflowRatioMin > 1.0) {
        clientErrors.push("สัดส่วนเงินออกขั้นต่ำ (outflow_ratio_min) ต้องอยู่ระหว่าง 0 ถึง 1.00 (ไม่เกิน 100%)");
    }
    if (isNaN(windowDays) || windowDays < 1) {
        clientErrors.push("กรอบเวลา (window_days) ต้องเป็นจำนวนเต็มตั้งแต่ 1 วันขึ้นไป");
    }

    if (clientErrors.length > 0) {
        if (errBox) {
            errBox.innerHTML = `<strong>⚠️ ข้อผิดพลาด:</strong><ul style="margin-left: 1.2rem; margin-top: 0.3rem;">${clientErrors.map(e => `<li>${e}</li>`).join("")}</ul>`;
            errBox.style.display = "block";
        }
        return;
    }

    const btn = document.getElementById("btn-calc-fast-in-out");
    if (btn) btn.disabled = true;

    try {
        const url = `/api/v1/fast-in-out?large_in_min=${largeInMin}&outflow_ratio_min=${outflowRatioMin}&window_days=${windowDays}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            if (errBox) {
                const msgs = errData.errors || (errData.detail ? [JSON.stringify(errData.detail)] : ["API request failed"]);
                errBox.innerHTML = `<strong>⚠️ ข้อผิดพลาด:</strong><ul style="margin-left: 1.2rem; margin-top: 0.3rem;">${msgs.map(e => `<li>${e}</li>`).join("")}</ul>`;
                errBox.style.display = "block";
            }
            return;
        }

        const res = await response.json();
        if (res.status === "ERROR") {
            if (errBox) {
                errBox.innerHTML = `<strong>⚠️ ข้อผิดพลาด:</strong><ul style="margin-left: 1.2rem; margin-top: 0.3rem;">${(res.errors || []).map(e => `<li>${e}</li>`).join("")}</ul>`;
                errBox.style.display = "block";
            }
            return;
        }

        updateFastInOutUI(res);
    } catch (err) {
        console.error("Error evaluating FAST_IN_OUT_3D:", err);
        if (errBox) {
            errBox.innerHTML = `<strong>⚠️ ขัดข้อง:</strong> ไม่สามารถเชื่อมต่อ API ได้`;
            errBox.style.display = "block";
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

function updateFastInOutUI(res) {
    if (!res) return;

    const totalValidElem = document.getElementById("fio-total-valid-val");
    if (totalValidElem) totalValidElem.textContent = (res.total_valid_transactions || 0).toLocaleString();

    const auditedElem = document.getElementById("fio-audited-val");
    if (auditedElem) auditedElem.textContent = (res.audited_count || 0).toLocaleString();

    const flaggedElem = document.getElementById("fio-flagged-val");
    if (flaggedElem) flaggedElem.textContent = (res.flagged_count || 0).toLocaleString();

    const accountsElem = document.getElementById("fio-flagged-accounts-sub");
    if (accountsElem) accountsElem.textContent = `จำนวนบัญชีที่พบ: ${res.flagged_accounts_count || 0} บัญชี`;

    const badgeElem = document.getElementById("fio-status-badge");
    if (badgeElem) {
        const status = res.review_status || "REVIEW";
        badgeElem.textContent = status;
        if (status === "REVIEW") {
            badgeElem.className = "badge-tag badge-review";
        } else {
            badgeElem.className = "badge-tag badge-pass";
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
    
    // Cash Flow Drain
    const cfAccounts = anom.cashflow_drain_accounts || 0;
    const cfWindows = anom.cashflow_drain_windows || 0;
    document.getElementById("cashflow-drain-val").textContent = cfAccounts;
    document.getElementById("cashflow-drain-sub").textContent = `Windows: ${cfWindows}`;

    if (anom.fast_in_out_3d) {
        updateFastInOutUI(anom.fast_in_out_3d);
    }
}

function formatTHB(num) {
    return new Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" }).format(num);
}

