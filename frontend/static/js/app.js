/* global state */
let sessionId = null;
let pollTimer = null;

const API = (path) => `/api${path}`;

// ── DOM helpers ────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showStatus(msg, type = "processing") {
    const bar = $("statusBar");
    bar.className = `status-bar show ${type}`;
    bar.querySelector(".status-msg").textContent = msg;
    bar.querySelector(".spinner").style.display = type === "processing" ? "block" : "none";
    bar.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function showTab(name) {
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    $(name + "Panel").classList.add("active");
    document.querySelector(`.nav-item[data-tab="${name}"]`).classList.add("active");
}

// ── Path → URL conversion (CRITICAL: must strip absolute prefix correctly) ──
// Server mounts DATA_DIR at /data, e.g.:
//   /Users/.../FindMeApp/data/sessions/uuid/... → /data/sessions/uuid/...

function pathToUrl(filePath) {
    const marker = "/sessions/";
    const idx = filePath.indexOf(marker);
    if (idx !== -1) return "/data" + filePath.slice(idx);
    return filePath;
}

// ── Lightbox ───────────────────────────────────────────────────────────────

function openLightbox(src) {
    const lb = $("lightbox");
    $("lightboxImg").src = src;
    lb.classList.add("show");
}

function closeLightbox() {
    $("lightbox").classList.remove("show");
}

// ── Drag-and-drop upload zones ─────────────────────────────────────────────

function setupDropZone(zoneId, inputId, onFiles) {
    const zone = $(zoneId);
    const input = $(inputId);

    input.addEventListener("change", () => { onFiles(Array.from(input.files)); input.value = ""; });

    // Drag events land on the input (it covers the zone); toggle visual state on the zone
    input.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
    input.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    input.addEventListener("drop", e => {
        e.preventDefault();
        zone.classList.remove("drag-over");
        onFiles(Array.from(e.dataTransfer.files));
    });
}

// ── Session management ─────────────────────────────────────────────────────

async function ensureSession() {
    if (sessionId) return;
    const res = await fetch(API("/sessions"), { method: "POST" });
    const data = await res.json();
    sessionId = data.session_id;
    $("sessionIdDisplay").textContent = `Session: ${sessionId.slice(0, 8)}…`;
}

// ── Reference photo upload ─────────────────────────────────────────────────

let refFiles = [];

function addRefFiles(files) {
    refFiles = [...refFiles, ...files];
    renderRefPreview();
}

function renderRefPreview() {
    const container = $("refPreview");
    container.innerHTML = "";
    refFiles.forEach(f => {
        const url = URL.createObjectURL(f);
        const img = document.createElement("img");
        img.src = url;
        img.style.cssText = "width:80px;height:80px;object-fit:cover;border-radius:8px;margin:4px;border:2px solid var(--border);";
        container.appendChild(img);
    });
    $("refCount").textContent = refFiles.length > 0
        ? `✅ 已选 ${refFiles.length} 张参考自拍`
        : "";
}

// ── Media file upload ──────────────────────────────────────────────────────

let mediaFiles = [];

function addMediaFiles(files) {
    mediaFiles = [...mediaFiles, ...files];
    renderMediaTags();
}

function renderMediaTags() {
    const container = $("mediaFileList");
    container.innerHTML = "";
    mediaFiles.forEach(f => {
        const tag = document.createElement("span");
        tag.className = "file-tag";
        tag.textContent = `${f.type.startsWith("video/") ? "🎬" : "🖼"} ${f.name}`;
        container.appendChild(tag);
    });
    $("mediaCount").textContent = mediaFiles.length > 0
        ? `✅ 已选 ${mediaFiles.length} 个素材文件`
        : "";
}

// ── Upload helpers ─────────────────────────────────────────────────────────

async function uploadFiles(endpoint, files) {
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    const res = await fetch(endpoint, { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
}

// ── Find Me (Feature A) ────────────────────────────────────────────────────

async function startFindMe() {
    if (refFiles.length === 0) {
        $("findHint").textContent = "⚠️ 请先在第一步选择参考自拍";
        alert("请先在第一步选择 1–3 张本人参考自拍");
        return;
    }
    if (mediaFiles.length === 0) {
        $("findHint").textContent = "⚠️ 请先在第二步添加要搜索的照片或视频";
        alert("请先在第二步添加要搜索的照片或视频");
        return;
    }

    $("findHint").textContent = "";
    const btn = $("findBtn");
    btn.disabled = true;
    showStatus("正在上传文件…");

    try {
        await ensureSession();
        await uploadFiles(API(`/sessions/${sessionId}/references`), refFiles);
        await uploadFiles(API(`/sessions/${sessionId}/media`), mediaFiles);

        showStatus("正在识别 — 检测照片和视频中的人脸…");
        const resp = await fetch(API(`/sessions/${sessionId}/find`), { method: "POST" });
        if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);

        pollStatus();
    } catch (e) {
        $("findHint").textContent = `❌ ${e.message}`;
        alert(`错误: ${e.message}`);
        showStatus(`错误: ${e.message}`, "error");
        btn.disabled = false;
    }
}

function pollStatus() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const state = await fetch(API(`/sessions/${sessionId}`)).then(r => r.json());
            const statusLabels = {
                processing: "处理中…",
                processing_photos: "正在识别照片…",
                processing_videos: "正在识别视频…",
                done: "完成！",
                error: "出错了",
            };
            if (state.status === "done") {
                clearInterval(pollTimer);
                showStatus("识别完成！结果已就绪。", "done");
                renderResults(state.results);
                $("findBtn").disabled = false;
            } else if (state.status === "error") {
                clearInterval(pollTimer);
                showStatus(`错误: ${state.error || "未知错误"}`, "error");
                $("findBtn").disabled = false;
            } else {
                showStatus(statusLabels[state.status] || `${state.status}…`);
            }
        } catch { /* network blip, keep polling */ }
    }, 2000);
}

// ── Render results ─────────────────────────────────────────────────────────

function renderResults(results) {
    showTab("results");

    // ── Photos ──
    const photoOutput = results.photos?.output;
    const photoGrid = $("photoGrid");
    photoGrid.innerHTML = "";

    if (photoOutput?.matched_paths?.length > 0) {
        $("photoStat").textContent =
            `在 ${photoOutput.total} 张照片中找到 ${photoOutput.matched_count} 张含有你的照片`;

        photoOutput.matched_paths.forEach(p => {
            const url = pathToUrl(p);
            const div = document.createElement("div");
            div.className = "photo-thumb";
            div.title = p.split("/").pop();

            const img = document.createElement("img");
            img.src = url;
            img.loading = "lazy";
            img.onerror = () => { div.style.background = "var(--border)"; img.style.display = "none"; };
            img.addEventListener("click", () => openLightbox(url));

            div.appendChild(img);
            photoGrid.appendChild(div);
        });
    } else {
        $("photoStat").textContent = "未找到含有你的照片。";
    }

    // ── Video clips ──
    const videoOutput = results.videos?.output;
    const clipList = $("clipList");
    clipList.innerHTML = "";

    if (videoOutput?.videos?.length > 0) {
        let totalClips = 0;
        videoOutput.videos.forEach(v => {
            (v.clips || []).forEach(c => {
                totalClips++;
                const url = pathToUrl(c.path);
                const filename = c.path.split("/").pop();
                const dur = (c.end_s - c.start_s).toFixed(1);

                const card = document.createElement("div");
                card.className = "clip-card";

                const video = document.createElement("video");
                video.src = url;
                video.controls = true;
                video.preload = "metadata";
                video.onerror = () => { video.style.display = "none"; };

                const info = document.createElement("div");
                info.className = "clip-info";

                const name = document.createElement("div");
                name.className = "clip-name";
                name.textContent = filename;

                const time = document.createElement("div");
                time.className = "clip-time";
                time.textContent = `${c.start_s}s – ${c.end_s}s（时长 ${dur}s）`;

                info.appendChild(name);
                info.appendChild(time);
                card.appendChild(video);
                card.appendChild(info);
                clipList.appendChild(card);
            });
        });
        $("clipStat").textContent = `找到 ${totalClips} 个视频片段`;
    } else {
        $("clipStat").textContent = "未找到含有你的视频片段。";
    }
}

// ── Feature B: Highlight ───────────────────────────────────────────────────

async function buildHighlight() {
    if (!sessionId) { alert('请先完成"找我"步骤。'); return; }
    const btn = $("highlightBtn");
    btn.disabled = true;
    $("highlightStatus").textContent = "正在生成高光视频…";

    await fetch(API(`/sessions/${sessionId}/highlight`), { method: "POST" });

    const pollH = setInterval(async () => {
        try {
            const state = await fetch(API(`/sessions/${sessionId}`)).then(r => r.json());
            if (state.highlight_status === "done") {
                clearInterval(pollH);
                const hPath = state.results?.highlight?.output?.highlight_video_path;
                if (hPath) {
                    const vid = $("highlightVideo");
                    vid.src = pathToUrl(hPath);
                    vid.style.display = "block";
                    $("highlightStatus").textContent = "高光视频已生成！";
                } else {
                    $("highlightStatus").textContent = "未能生成视频。";
                }
                btn.disabled = false;
            } else if (state.highlight_status === "error") {
                clearInterval(pollH);
                $("highlightStatus").textContent = `错误: ${state.results?.highlight?.error || "未知错误"}`;
                btn.disabled = false;
            }
        } catch { /* keep polling */ }
    }, 2000);
}

// ── Feature C: Travel Map ──────────────────────────────────────────────────

let amapInstance = null;
let routePoints = [];      // validated points with display coords
let travelerMarker = null;
let activeLine = null;
let routePlaying = false;
let rafId = null;

// Separate markers that are too close to see (< 0.005° ≈ 500m apart)
function separateOverlapping(points) {
    const THRESHOLD = 0.005;
    const result = points.map(p => ({ ...p, dispLng: p.lng, dispLat: p.lat }));
    for (let i = 0; i < result.length; i++) {
        for (let j = i + 1; j < result.length; j++) {
            const dLat = Math.abs(result[j].lat - result[i].lat);
            const dLng = Math.abs(result[j].lng - result[i].lng);
            if (dLat < THRESHOLD && dLng < THRESHOLD) {
                // nudge j slightly north-east so both markers are visible
                result[j].dispLat += THRESHOLD * 0.8;
                result[j].dispLng += THRESHOLD * 0.8;
            }
        }
    }
    return result;
}

function buildThumbMarker(point, index) {
    const div = document.createElement("div");
    div.className = "map-thumb-marker";
    div.setAttribute("data-idx", index);
    const img = document.createElement("img");
    img.src = point.photo_url;
    img.onerror = () => { div.style.background = "var(--accent)"; div.innerHTML = `<span style="color:#fff;font-size:18px;line-height:56px;display:block;text-align:center">📍</span>`; };
    div.appendChild(img);
    return div;
}

async function loadTravelMap() {
    if (!sessionId) { alert('请先完成"找我"步骤。'); return; }

    $("mapInfo").textContent = "正在加载地图数据…";
    const data = await fetch(API(`/sessions/${sessionId}/map`)).then(r => r.json());

    if (!data.map_points?.length) {
        $("mapInfo").textContent = "找到的照片中没有 GPS 信息。";
        return;
    }

    const valid = data.map_points.filter(p => p.has_gps);
    $("mapInfo").textContent = `共 ${data.total} 个点位，${data.missing_gps_count} 个缺少 GPS`;
    if (!valid.length) return;

    if (amapReady) {
        try { await amapReady; }
        catch { $("mapInfo").textContent = "高德地图 SDK 加载失败，请检查网络。"; return; }
    }
    if (typeof AMap === "undefined") {
        $("mapInfo").textContent += "（高德地图未加载 — 请在 config/.env 中设置 AMAP_KEY）";
        return;
    }

    if (amapInstance) { amapInstance.destroy(); amapInstance = null; }
    routePoints = separateOverlapping(valid);

    amapInstance = new AMap.Map("mapContainer", {
        zoom: 5,
        center: [routePoints[0].dispLng, routePoints[0].dispLat],
        mapStyle: "amap://styles/dark",
    });

    // Full dim route line
    new AMap.Polyline({
        path: routePoints.map(p => [p.dispLng, p.dispLat]),
        strokeColor: "#4a4870",
        strokeWeight: 3,
        strokeDasharray: [8, 4],
        map: amapInstance,
    });

    // Thumbnail markers
    routePoints.forEach((p, i) => {
        const el = buildThumbMarker(p, i);
        const marker = new AMap.Marker({
            position: [p.dispLng, p.dispLat],
            content: el,
            offset: new AMap.Pixel(-28, -28),
            map: amapInstance,
            zIndex: 100 + i,
        });
        p._marker = marker;
        el.addEventListener("click", () => showRouteImage(p, i));
    });

    amapInstance.setFitView(null, false, [40, 40, 40, 40]);

    $("playRouteBtn").style.display = "inline-flex";
    $("loadMapBtn").textContent = "🔄 重新加载";
}

// Show fullscreen photo overlay for HOLD_MS ms, returns a Promise
function showRouteImage(point, index) {
    const HOLD_MS = 2000;
    return new Promise(resolve => {
        const overlay = $("routeOverlay");
        const img = $("routeOverlayImg");
        const caption = $("routeOverlayCaption");
        const bar = $("routeOverlayBar");

        img.src = point.photo_url;
        caption.textContent = `${index + 1} / ${routePoints.length}  ${point.taken_at || ""}`;
        bar.style.transition = "none";
        bar.style.width = "0%";
        overlay.classList.add("show");

        // highlight active marker
        routePoints.forEach((p, i) => {
            p._marker?.getContent()?.classList.toggle("active", i === index);
        });

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                bar.style.transition = `width ${HOLD_MS}ms linear`;
                bar.style.width = "100%";
            });
        });

        setTimeout(() => {
            overlay.classList.remove("show");
            resolve();
        }, HOLD_MS);
    });
}

// Animate traveler from pointA to pointB over TRAVEL_MS ms
function animateTravel(fromPt, toPt, TRAVEL_MS = 1800) {
    return new Promise(resolve => {
        if (!travelerMarker) {
            const el = document.createElement("div");
            el.className = "map-traveler";
            el.textContent = "✈";
            travelerMarker = new AMap.Marker({
                content: el,
                offset: new AMap.Pixel(-14, -14),
                map: amapInstance,
                zIndex: 300,
            });
        }
        // Active path line (grows as traveler moves)
        if (activeLine) { activeLine.setMap(null); activeLine = null; }
        activeLine = new AMap.Polyline({
            path: [[fromPt.dispLng, fromPt.dispLat]],
            strokeColor: "#6c63ff",
            strokeWeight: 4,
            map: amapInstance,
        });

        const startTime = performance.now();
        function frame(now) {
            const t = Math.min((now - startTime) / TRAVEL_MS, 1);
            const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; // ease-in-out
            const lng = fromPt.dispLng + (toPt.dispLng - fromPt.dispLng) * ease;
            const lat = fromPt.dispLat + (toPt.dispLat - fromPt.dispLat) * ease;
            travelerMarker.setPosition([lng, lat]);
            activeLine.setPath([
                [fromPt.dispLng, fromPt.dispLat],
                [lng, lat],
            ]);
            if (t < 1) { rafId = requestAnimationFrame(frame); }
            else { resolve(); }
        }
        rafId = requestAnimationFrame(frame);
    });
}

async function playRoute() {
    if (routePlaying || routePoints.length < 1) return;
    routePlaying = true;
    $("playRouteBtn").disabled = true;
    $("playRouteBtn").textContent = "⏳ 播放中…";

    // Reset active line
    if (activeLine) { activeLine.setMap(null); activeLine = null; }
    if (travelerMarker) { travelerMarker.setPosition([routePoints[0].dispLng, routePoints[0].dispLat]); }

    for (let i = 0; i < routePoints.length; i++) {
        await showRouteImage(routePoints[i], i);
        if (i < routePoints.length - 1) {
            await animateTravel(routePoints[i], routePoints[i + 1]);
        }
    }

    if (travelerMarker) { travelerMarker.setMap(null); travelerMarker = null; }
    if (activeLine) { activeLine.setMap(null); activeLine = null; }
    routePoints.forEach(p => p._marker?.getContent()?.classList.remove("active"));

    routePlaying = false;
    $("playRouteBtn").disabled = false;
    $("playRouteBtn").textContent = "▶ 播放轨迹";
}

// ── Amap SDK dynamic load ──────────────────────────────────────────────────

let amapReady = null;  // Promise that resolves when AMap SDK is loaded

async function loadAmapSDK() {
    try {
        const cfg = await fetch(API("/config")).then(r => r.json());
        if (!cfg.amap_key || cfg.amap_key === "your_amap_key_here") return;
        amapReady = new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = `https://webapi.amap.com/maps?v=2.0&key=${cfg.amap_key}&plugin=AMap.Polyline,AMap.Marker,AMap.InfoWindow`;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    } catch { /* amap unavailable */ }
}

// ── Init ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    // Navigation
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", () => showTab(item.dataset.tab));
    });

    // Upload zones
    setupDropZone("refZone", "refInput", addRefFiles);
    setupDropZone("mediaZone", "mediaInput", addMediaFiles);

    // Buttons
    $("findBtn").addEventListener("click", startFindMe);
    $("highlightBtn").addEventListener("click", buildHighlight);
    $("loadMapBtn").addEventListener("click", loadTravelMap);
    $("playRouteBtn").addEventListener("click", playRoute);

    // Lightbox
    $("lightbox").addEventListener("click", e => {
        if (e.target === $("lightbox") || e.target === $("lightboxClose")) closeLightbox();
    });
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeLightbox(); });

    // Load Amap SDK
    loadAmapSDK();
});
