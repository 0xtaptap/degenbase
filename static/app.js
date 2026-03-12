/**
 * DEGEN Command Center — Frontend Application
 * Tabs: Command Center, Wallet Explorer, Twitter Pulse
 */

// === State ===
const state = {
    currentTab: 'command',
    dashboardData: null,
    pulseLoaded: false,
    teamLoaded: false,
    activityLoaded: false,
    statsLoaded: false,
    whalesLoaded: false
};

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadTokenStats();
    loadWhales();
    loadNetworkActivity();
    generateSparkles();
});

// === Sparkle Generator ===
function generateSparkles() {
    const field = document.getElementById('sparkleField');
    if (!field) return;
    for (let i = 0; i < 30; i++) {
        const dot = document.createElement('div');
        dot.className = 'sparkle';
        dot.style.left = Math.random() * 100 + '%';
        dot.style.top = Math.random() * 100 + '%';
        dot.style.animationDelay = (Math.random() * 5) + 's';
        dot.style.animationDuration = (2 + Math.random() * 4) + 's';
        field.appendChild(dot);
    }
}

// === Tab Navigation ===
function initTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });

    // X-Ray enter key
    const xrayInput = document.getElementById('xrayInput');
    if (xrayInput) {
        xrayInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') runXray();
        });
    }
}

function switchTab(tabName) {
    state.currentTab = tabName;

    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${tabName}`).classList.add('active');

    // Lazy-load
    if (tabName === 'twitter' && !state.pulseLoaded) {
        loadPulse();
        loadTeamTweets();
    }
    if (tabName === 'explorer' && !state.activityLoaded) {
        loadNetworkActivity();
    }
}

// === Command Center: Token Stats ===
async function loadTokenStats() {
    try {
        const resp = await fetch('/api/token/stats');
        const data = await resp.json();
        state.statsLoaded = true;

        document.getElementById('statPrice').textContent = data.price_formatted || '$0.00';
        document.getElementById('statMcap').textContent = data.market_cap_formatted || '$0';
        document.getElementById('statVolume').textContent = data.volume_24h_formatted || '$0';
        document.getElementById('statLiquidity').textContent = data.liquidity_formatted || '$0';

        const changeEl = document.getElementById('statChange');
        const change = data.price_change_24h || 0;
        changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
        changeEl.className = `stat-pill-change ${change >= 0 ? 'positive' : 'negative'}`;

    } catch (err) {
        console.error('Token stats error:', err);
    }
}

// === Command Center: Whale Watch ===
async function loadWhales() {
    const list = document.getElementById('whaleList');

    try {
        const resp = await fetch('/api/whales/recent');
        const data = await resp.json();
        state.whalesLoaded = true;

        const whales = data.whales || [];
        if (whales.length === 0) {
            list.innerHTML = `
                <div class="xray-empty">
                    <div class="empty-icon">🐋</div>
                    <div class="empty-desc">No whale activity detected. Check back soon!</div>
                </div>`;
            return;
        }

        list.innerHTML = whales.map((w, i) => {
            const icon = w.size === 'whale' ? '🐋' : w.size === 'shark' ? '🦈' : '🐬';
            const sizeClass = `size-${w.size}`;
            const timeAgo = getTimeAgo(w.timestamp);

            return `
                <div class="whale-card ${sizeClass}" style="animation-delay: ${i * 0.05}s">
                    <span class="whale-icon">${icon}</span>
                    <div class="whale-addresses">
                        <div class="whale-flow">
                            ${w.from} <span class="arrow">→</span> ${w.to}
                        </div>
                    </div>
                    <div style="text-align:right">
                        <div class="whale-amount">${w.value_formatted} DEGEN</div>
                        <div class="whale-time">${timeAgo}</div>
                    </div>
                </div>`;
        }).join('');

    } catch (err) {
        list.innerHTML = `
            <div class="xray-empty">
                <div class="empty-icon">⚠️</div>
                <div class="empty-desc">Error loading whale data</div>
            </div>`;
    }
}

// === Command Center: Wallet X-Ray ===
async function runXray() {
    const address = document.getElementById('xrayInput').value.trim();
    if (!address.startsWith('0x') || address.length !== 42) {
        showToast('Enter a valid wallet address (0x...)', 'error');
        return;
    }

    const results = document.getElementById('xrayResults');
    const loading = document.getElementById('xrayLoading');
    const empty = document.getElementById('xrayEmpty');

    results.style.display = 'none';
    empty.style.display = 'none';
    loading.style.display = 'flex';

    try {
        const resp = await fetch(`/api/wallet/xray/${address}`);
        const data = await resp.json();

        document.getElementById('xrayBalance').textContent = data.balance_formatted;
        document.getElementById('xrayUsd').textContent = data.usd_value_formatted;
        document.getElementById('xrayAddress').textContent = data.address;
        document.getElementById('xrayTotalTx').textContent = data.total_transfers;
        document.getElementById('xrayReceived').textContent = data.total_received_formatted;
        document.getElementById('xraySent').textContent = data.total_sent_formatted;
        document.getElementById('xrayLargest').textContent = data.largest_tx.value_formatted + ' DEGEN';

        // OG date
        const ogEl = document.getElementById('xrayOg');
        if (data.first_interaction) {
            const firstDate = new Date(data.first_interaction);
            ogEl.textContent = `🎩 DEGEN OG since ${firstDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}`;
            ogEl.style.display = 'block';
        } else {
            ogEl.style.display = 'none';
        }

        loading.style.display = 'none';
        results.style.display = 'block';

    } catch (err) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        showToast('Error scanning wallet', 'error');
    }
}

// === Wallet Explorer ===
async function searchWallet() {
    const wallet = document.getElementById('walletSearch').value.trim();
    if (!wallet.startsWith('0x') || wallet.length !== 42) {
        showToast('Enter a valid Ethereum address (0x...)', 'error');
        return;
    }

    const results = document.getElementById('dashboardResults');
    const loading = document.getElementById('dashboardLoading');
    const empty = document.getElementById('dashboardEmpty');

    results.style.display = 'none';
    empty.style.display = 'none';
    loading.style.display = 'flex';

    try {
        const resp = await fetch(`/api/onchain/${wallet}`);
        const data = await resp.json();
        state.dashboardData = data;

        const balance = data.balance || {};
        document.getElementById('balanceValue').textContent = balance.balance_formatted || '0';
        document.getElementById('balanceRaw').textContent = `${(balance.balance || 0).toLocaleString()} DEGEN tokens`;
        document.getElementById('balanceWallet').textContent = wallet;

        const transfers = data.transfers || {};
        document.getElementById('statReceived').textContent = transfers.total_received || 0;
        document.getElementById('statSent').textContent = transfers.total_sent || 0;
        document.getElementById('statTotal').textContent = (transfers.total_received || 0) + (transfers.total_sent || 0);

        renderTransfers(transfers.transfers || []);

        loading.style.display = 'none';
        results.style.display = 'block';

    } catch (err) {
        loading.style.display = 'none';
        empty.style.display = 'block';
        showToast('Error fetching wallet data', 'error');
    }
}

function renderTransfers(transfers) {
    const list = document.getElementById('transferList');

    if (transfers.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-title">No Transfers Found</div>
                <div class="empty-desc">This wallet has no recent DEGEN transfers.</div>
            </div>`;
        return;
    }

    list.innerHTML = transfers.map((t, i) => {
        const isReceived = t.type === 'received';
        const icon = isReceived ? '📥' : '📤';
        const dirClass = isReceived ? 'received' : 'sent';
        const sign = isReceived ? '+' : '-';
        const otherAddr = isReceived ? (t.from || 'unknown') : (t.to || 'unknown');
        const shortAddr = otherAddr.length > 10 ? `${otherAddr.slice(0, 6)}...${otherAddr.slice(-4)}` : otherAddr;
        const timeAgo = getTimeAgo(t.timestamp);

        return `
            <div class="transfer-item" style="animation-delay: ${i * 0.04}s">
                <div class="transfer-direction">
                    <div class="transfer-icon ${dirClass}">${icon}</div>
                    <div>
                        <div class="transfer-label">${isReceived ? 'Received from' : 'Sent to'}</div>
                        <div class="transfer-address">${shortAddr}</div>
                    </div>
                </div>
                <div style="text-align:right">
                    <div class="transfer-value ${dirClass}">${sign}${t.value_formatted || t.value} DEGEN</div>
                    <div class="transfer-time">${timeAgo}</div>
                </div>
            </div>`;
    }).join('');
}

async function loadNetworkActivity() {
    const list = document.getElementById('activityList');

    try {
        const resp = await fetch('/api/onchain/activity/recent');
        const data = await resp.json();
        state.activityLoaded = true;

        const activity = data.activity || [];
        if (activity.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">⚡</div>
                    <div class="empty-title">No Recent Activity</div>
                    <div class="empty-desc">Check back soon for live DEGEN transfers.</div>
                </div>`;
            return;
        }

        list.innerHTML = activity.map((a, i) => {
            const timeAgo = getTimeAgo(a.timestamp);
            return `
                <div class="transfer-item" style="animation-delay: ${i * 0.04}s">
                    <div class="transfer-direction">
                        <div class="transfer-icon received">⚡</div>
                        <div>
                            <div class="transfer-address">${a.from} → ${a.to}</div>
                        </div>
                    </div>
                    <div style="text-align:right">
                        <div class="transfer-value received">${a.value_formatted} DEGEN</div>
                        <div class="transfer-time">${timeAgo}</div>
                    </div>
                </div>`;
        }).join('');

    } catch (err) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Cannot Load Activity</div>
                <div class="empty-desc">Check your Alchemy API key in .env</div>
            </div>`;
    }
}

// === Twitter Pulse ===
async function loadPulse() {
    const list = document.getElementById('pulseList');

    try {
        const resp = await fetch('/api/twitter/pulse');
        const data = await resp.json();
        state.pulseLoaded = true;

        const tweets = data.tweets || [];
        // Update pulse counter
        const pulseCountEl = document.getElementById('pulseCount');
        if (pulseCountEl) pulseCountEl.textContent = tweets.length;

        if (tweets.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📡</div>
                    <div class="empty-title">No Tweets Yet</div>
                    <div class="empty-desc">Add your Twitter credentials to .env to see live DEGEN community tweets.</div>
                </div>`;
            return;
        }

        // Find max engagement for relative bar sizing
        const maxEngagement = Math.max(1, ...tweets.map(t => (t.like_count || 0) + (t.retweet_count || 0)));
        list.innerHTML = tweets.map((t, i) => renderTweetCard(t, i, false, maxEngagement)).join('');

    } catch (err) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Pulse Unavailable</div>
                <div class="empty-desc">Server error loading tweets.</div>
            </div>`;
    }
}

async function loadTeamTweets() {
    const list = document.getElementById('teamList');

    try {
        const resp = await fetch('/api/twitter/team');
        const data = await resp.json();
        state.teamLoaded = true;

        const tweets = data.tweets || [];
        // Update team counter
        const teamCountEl = document.getElementById('teamCount');
        if (teamCountEl) teamCountEl.textContent = tweets.length;

        if (tweets.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">👑</div>
                    <div class="empty-title">Team Feed Empty</div>
                    <div class="empty-desc">Configure DEGEN_TEAM_ACCOUNTS in .env to track team tweets.</div>
                </div>`;
            return;
        }

        const maxEngagement = Math.max(1, ...tweets.map(t => (t.like_count || 0) + (t.retweet_count || 0)));
        list.innerHTML = tweets.map((t, i) => renderTweetCard(t, i, true, maxEngagement)).join('');

    } catch (err) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Team Feed Unavailable</div>
                <div class="empty-desc">Server error loading team tweets.</div>
            </div>`;
    }
}

function renderTweetCard(tweet, index, isTeam, maxEngagement = 100) {
    const avatarHtml = tweet.profile_image
        ? `<img src="${escapeHtml(tweet.profile_image)}" class="tweet-avatar" alt="${escapeHtml(tweet.username)}" onerror="this.outerHTML='<div class=\\'tweet-avatar-placeholder\\'>🎩</div>'">`
        : `<div class="tweet-avatar-placeholder">🎩</div>`;

    const teamClass = isTeam || tweet.team_member ? 'team-tweet' : '';
    const timeAgo = getTimeAgo(tweet.created_at);
    const tweetUrl = tweet.url ? `onclick="window.open('${escapeHtml(tweet.url)}', '_blank')" style="cursor:pointer"` : '';

    // Engagement bar
    const engagement = (tweet.like_count || 0) + (tweet.retweet_count || 0);
    const engagementPct = Math.min(100, Math.round((engagement / maxEngagement) * 100));
    const engagementBar = engagement > 0
        ? `<div class="tweet-engagement"><div class="tweet-engagement-fill" style="width:${engagementPct}%"></div></div>`
        : '';

    return `
        <div class="tweet-card ${teamClass}" style="animation-delay: ${index * 0.06}s" ${tweetUrl}>
            <div class="tweet-header">
                ${avatarHtml}
                <div class="tweet-user-info">
                    <div class="tweet-display-name">${escapeHtml(tweet.display_name || tweet.username)}</div>
                    <div class="tweet-username">@${escapeHtml(tweet.username)}</div>
                </div>
                <div class="tweet-time">${timeAgo}</div>
            </div>
            <div class="tweet-text">${highlightDegenMentions(escapeHtml(tweet.text))}</div>
            <div class="tweet-footer">
                <span class="tweet-stat">💬 ${tweet.reply_count || 0}</span>
                <span class="tweet-stat">🔄 ${tweet.retweet_count || 0}</span>
                <span class="tweet-stat">❤️ ${tweet.like_count || 0}</span>
            </div>
            ${engagementBar}
        </div>`;
}

// === Utilities ===
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function highlightDegenMentions(text) {
    return text
        .replace(/(\$DEGEN)/gi, '<span style="color: var(--purple-600); font-weight: 700;">$1</span>')
        .replace(/(#DEGEN)/gi, '<span style="color: var(--purple-600); font-weight: 700;">$1</span>')
        .replace(/(@\w+)/g, '<span style="color: var(--purple-500); font-weight: 600;">$1</span>');
}

function getTimeAgo(timestamp) {
    if (!timestamp) return '';
    try {
        const now = new Date();
        const then = new Date(timestamp);
        const diffMs = now - then;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return then.toLocaleDateString();
    } catch {
        return '';
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// === Auto-refresh ===
setInterval(() => {
    if (state.currentTab === 'command') {
        loadTokenStats();
        loadWhales();
    }
    if (state.currentTab === 'twitter' && state.pulseLoaded) {
        loadPulse();
        loadTeamTweets();
    }
}, 30000);

// === Keyboard shortcuts ===
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.id === 'walletSearch') {
        searchWallet();
    }
});
