/**
 * Degen Dream Hub — Frontend Application
 * Handles tab navigation, API calls, rendering, and animations.
 */

// === State ===
const state = {
    currentTab: 'dreams',
    dreams: [],
    dashboardData: null,
    pulseLoaded: false,
    teamLoaded: false,
    activityLoaded: false
};

// === Initialization ===
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadDreams();
    loadNetworkActivity();
});

// === Tab Navigation ===
function initTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    state.currentTab = tabName;

    // Update nav buttons
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update panels
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${tabName}`).classList.add('active');

    // Lazy-load tab content
    if (tabName === 'twitter' && !state.pulseLoaded) {
        loadPulse();
        loadTeamTweets();
    }
    if (tabName === 'dashboard' && !state.activityLoaded) {
        loadNetworkActivity();
    }
}

// === Dream Board ===
async function loadDreams() {
    const grid = document.getElementById('dreamGrid');
    const loading = document.getElementById('dreamsLoading');

    try {
        const resp = await fetch('/api/dreams');
        const data = await resp.json();
        state.dreams = data.dreams || [];

        // Update count badge
        document.getElementById('dreams-count').textContent = state.dreams.length;

        loading.style.display = 'none';

        if (state.dreams.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <div class="empty-icon">🎩</div>
                    <div class="empty-title">No Dreams Yet</div>
                    <div class="empty-desc">Be the first to share your degen dream! What are you building? What's your vision?</div>
                </div>`;
            return;
        }

        grid.innerHTML = state.dreams.map((d, i) => renderDreamCard(d, i)).join('');

    } catch (err) {
        loading.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Connection Error</div>
                <div class="empty-desc">Couldn't load dreams. Is the server running?</div>
            </div>`;
    }
}

function renderDreamCard(dream, index) {
    const imageHtml = dream.image_url ? `<img src="${escapeHtml(dream.image_url)}" class="dream-image" alt="Dream image" onerror="this.style.display='none'">` : '';
    const walletDisplay = dream.wallet ? `${dream.wallet.slice(0, 6)}...${dream.wallet.slice(-4)}` : 'anon';
    const balanceHtml = dream.degen_balance && parseFloat(dream.degen_balance) > 0
        ? `<span class="dream-balance">🎩 ${dream.degen_balance_formatted || dream.degen_balance} DEGEN</span>`
        : '';
    const timeAgo = getTimeAgo(dream.timestamp);

    return `
        <div class="dream-card" style="animation-delay: ${index * 0.06}s">
            ${imageHtml}
            <div class="dream-text">${escapeHtml(dream.text)}</div>
            <div class="dream-meta">
                <div>
                    <div class="dream-wallet">🔗 ${walletDisplay} ${balanceHtml}</div>
                    <div class="dream-time">${timeAgo}</div>
                </div>
                <div class="dream-actions">
                    <button class="btn-upvote" onclick="upvoteDream('${dream.id}', this)">
                        🔥 <span>${dream.upvotes || 0}</span>
                    </button>
                </div>
            </div>
        </div>`;
}

async function submitDream() {
    const text = document.getElementById('dreamText').value.trim();
    const imageUrl = document.getElementById('dreamImage').value.trim();
    const wallet = document.getElementById('dreamWallet').value.trim();

    if (!text) {
        showToast('Write your dream first! 🎩', 'error');
        return;
    }

    const btn = document.getElementById('btnSubmitDream');
    btn.disabled = true;
    btn.innerHTML = '⏳ Dropping...';

    try {
        const resp = await fetch('/api/dreams', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, image_url: imageUrl || null, wallet: wallet || null })
        });

        const data = await resp.json();
        if (data.success) {
            showToast('Dream dropped! 🎩🔥', 'success');
            document.getElementById('dreamText').value = '';
            document.getElementById('dreamImage').value = '';
            document.getElementById('dreamWallet').value = '';
            loadDreams();
        } else {
            showToast('Failed to submit dream', 'error');
        }
    } catch (err) {
        showToast('Server error — is the backend running?', 'error');
    }

    btn.disabled = false;
    btn.innerHTML = '🎩 Drop Dream';
}

async function upvoteDream(dreamId, btn) {
    try {
        const resp = await fetch('/api/dreams/upvote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dream_id: dreamId })
        });

        const data = await resp.json();
        if (data.success) {
            const countSpan = btn.querySelector('span');
            countSpan.textContent = data.upvotes;
            btn.style.borderColor = 'var(--purple-mid)';
            btn.style.color = 'var(--purple-light)';

            // Quick pulse animation
            btn.style.transform = 'scale(1.2)';
            setTimeout(() => { btn.style.transform = 'scale(1)'; }, 200);
        }
    } catch (err) {
        console.error('Upvote error:', err);
    }
}

// === On-Chain Dashboard ===
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

        // Render balance
        const balance = data.balance || {};
        document.getElementById('balanceValue').textContent = balance.balance_formatted || '0';
        document.getElementById('balanceRaw').textContent = `${(balance.balance || 0).toLocaleString()} DEGEN tokens`;
        document.getElementById('balanceWallet').textContent = wallet;

        // Render stats
        const transfers = data.transfers || {};
        document.getElementById('statReceived').textContent = transfers.total_received || 0;
        document.getElementById('statSent').textContent = transfers.total_sent || 0;
        document.getElementById('statTotal').textContent = (transfers.total_received || 0) + (transfers.total_sent || 0);

        // Render transfer list
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
    const loading = document.getElementById('activityLoading');

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
        if (loading) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div class="empty-title">Cannot Load Activity</div>
                    <div class="empty-desc">Check your Alchemy API key in .env</div>
                </div>`;
        }
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
        if (tweets.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📡</div>
                    <div class="empty-title">No Tweets Yet</div>
                    <div class="empty-desc">Add your Twitter credentials to .env to see live DEGEN community tweets.</div>
                </div>`;
            return;
        }

        list.innerHTML = tweets.map((t, i) => renderTweetCard(t, i, false)).join('');

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
        if (tweets.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">👑</div>
                    <div class="empty-title">Team Feed Empty</div>
                    <div class="empty-desc">Add Twitter credentials to see @degentokenbase and @BR4ted tweets.</div>
                </div>`;
            return;
        }

        list.innerHTML = tweets.map((t, i) => renderTweetCard(t, i, true)).join('');

    } catch (err) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Team Feed Unavailable</div>
                <div class="empty-desc">Server error loading team tweets.</div>
            </div>`;
    }
}

function renderTweetCard(tweet, index, isTeam) {
    const avatarHtml = tweet.profile_image
        ? `<img src="${escapeHtml(tweet.profile_image)}" class="tweet-avatar" alt="${escapeHtml(tweet.username)}" onerror="this.outerHTML='<div class=\\'tweet-avatar-placeholder\\'>🎩</div>'">`
        : `<div class="tweet-avatar-placeholder">🎩</div>`;

    const teamClass = isTeam || tweet.team_member ? 'team-tweet' : '';
    const timeAgo = getTimeAgo(tweet.created_at);

    const tweetUrl = tweet.url ? `onclick="window.open('${escapeHtml(tweet.url)}', '_blank')" style="cursor:pointer"` : '';

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
            <div class="tweet-stats">
                <span class="tweet-stat">💬 ${tweet.reply_count || 0}</span>
                <span class="tweet-stat">🔄 ${tweet.retweet_count || 0}</span>
                <span class="tweet-stat">❤️ ${tweet.like_count || 0}</span>
            </div>
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
        .replace(/(\$DEGEN)/gi, '<span style="color: var(--purple-light); font-weight: 600;">$1</span>')
        .replace(/(#DEGEN)/gi, '<span style="color: var(--purple-light); font-weight: 600;">$1</span>')
        .replace(/(@\w+)/g, '<span style="color: var(--accent-cyan);">$1</span>');
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
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// === Auto-refresh Twitter (every 60s when tab is active) ===
setInterval(() => {
    if (state.currentTab === 'twitter' && state.pulseLoaded) {
        loadPulse();
        loadTeamTweets();
    }
}, 60000);

// === Keyboard shortcuts ===
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.id === 'walletSearch') {
        searchWallet();
    }
});
