import { api } from './api.js';
import { utils } from './utils.js';

// === КОНФИГУРАЦИЯ ===
const CFG = {
    TILE_SIZE: 80,       // Увеличил размер тайла (было 64), чтобы влезало больше иконок
    ICON_SIZE: 22,       
    EVENT_SIZE: 26,      
    ANIMATION_SPEED: 800,
    COLORS: {
        'plain': '#4ade80', 'forest': '#166534', 'desert': '#fde047',
        'mountain': '#57534e', 'coast': '#3b82f6', 'swamp': '#4d7c0f',
        'tundra': '#cffafe', 'wasteland': '#78350f', 'default': '#2b2b2b'
    },
    // Описания для легенды
    LEGEND: {
        biomes: {
            'plain': 'Равнины', 'forest': 'Леса', 'desert': 'Пустыни',
            'mountain': 'Горы', 'swamp': 'Болота', 'coast': 'Побережье', 'tundra': 'Тундра'
        },
        events: {
            '⚔️': 'Война / Набег',
            '💀': 'Смерть / Истощение',
            '✨': 'Рождение / Открытие',
            '🏃': 'Миграция / Бегство',
            '🤝': 'Дипломатия'
        }
    }
};

// === КЛАСС ОТРИСОВКИ (View) ===
class WorldRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        
        this.layout = null;      
        this.entities = [];      
        this.history = {};       
        
        this.renderCache = new Map(); 

        this.camera = { x: 0, y: 0, zoom: 1.0 };
        this.isDragging = false;
        this.lastMouse = { x: 0, y: 0 };

        this._setupInput();
        this._createLegendOverlay(); // Создаем легенду при старте
    }

    _setupInput() {
        const resize = () => {
            if(!this.canvas.parentElement) return;
            this.canvas.width = this.canvas.parentElement.clientWidth;
            this.canvas.height = this.canvas.parentElement.clientHeight;
            this.draw(currentEpoch); 
        };
        window.addEventListener('resize', resize);
        setTimeout(resize, 100);

        this.canvas.addEventListener('wheel', e => {
            e.preventDefault();
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            this.camera.zoom = Math.max(0.1, Math.min(5.0, this.camera.zoom * factor));
            this.draw(currentEpoch);
        });

        this.canvas.addEventListener('mousedown', e => {
            this.isDragging = true;
            this.lastMouse = { x: e.offsetX, y: e.offsetY };
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', e => {
            if (!this.isDragging) return;
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            this.camera.x += (mouseX - this.lastMouse.x);
            this.camera.y += (mouseY - this.lastMouse.y);
            
            this.lastMouse = { x: mouseX, y: mouseY };
            this.draw(currentEpoch);
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            this.canvas.style.cursor = 'grab';
        });
    }

    // === НОВОЕ: Создание легенды ===
    _createLegendOverlay() {
        // Удаляем старую, если есть
        const old = document.getElementById('map-legend-overlay');
        if (old) old.remove();

        const container = document.createElement('div');
        container.id = 'map-legend-overlay';
        container.style.cssText = `
            position: absolute; top: 10px; right: 10px;
            background: rgba(30, 30, 30, 0.85); color: white;
            padding: 10px; border-radius: 8px; font-size: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            backdrop-filter: blur(4px); pointer-events: none;
            max-width: 200px;
        `;

        // Генерируем HTML для биомов
        let biomeHtml = '<div style="margin-bottom:8px; font-weight:bold; border-bottom:1px solid #555;">Биомы</div>';
        for (const [key, label] of Object.entries(CFG.LEGEND.biomes)) {
            const color = CFG.COLORS[key];
            biomeHtml += `
                <div style="display:flex; align-items:center; margin-bottom:2px;">
                    <div style="width:12px; height:12px; background:${color}; margin-right:8px; border:1px solid #fff;"></div>
                    <span>${label}</span>
                </div>`;
        }

        // Генерируем HTML для событий
        let eventHtml = '<div style="margin-top:8px; margin-bottom:4px; font-weight:bold; border-bottom:1px solid #555;">События</div>';
        for (const [icon, label] of Object.entries(CFG.LEGEND.events)) {
            eventHtml += `
                <div style="display:flex; align-items:center; margin-bottom:2px;">
                    <div style="width:16px; text-align:center; margin-right:8px;">${icon}</div>
                    <span>${label}</span>
                </div>`;
        }

        container.innerHTML = biomeHtml + eventHtml;
        
        // Вставляем внутрь родителя канваса
        this.canvas.parentElement.style.position = 'relative';
        this.canvas.parentElement.appendChild(container);
    }

    loadWorld(layout, entities) {
        this.layout = layout;
        this.updateEntities(entities);
        this.centerCamera();
    }

    loadHistory(historyLogs) {
        this.history = {};
        let maxAge = 0;
        
        historyLogs.forEach(line => {
            try {
                const evt = (typeof line === 'string') ? JSON.parse(line) : line;
                let age = 0;
                if (evt.created_at !== undefined) age = evt.created_at;
                else if (evt.age !== undefined) age = evt.age;
                else if (evt.data?.age !== undefined) age = evt.data.age;
                age = Number(age);

                if (age > maxAge) maxAge = age;
                if (!this.history[age]) this.history[age] = [];
                this.history[age].push(evt);
            } catch (e) {}
        });
        return maxAge;
    }

    updateEntities(newEntities) {
        this.entities = newEntities || [];
        this._rebuildCache();
    }

    // === ИСПРАВЛЕННЫЙ РАСЧЕТ ПОЗИЦИЙ (Anti-Overlap) ===
    _rebuildCache() {
        this.renderCache.clear();
        if (!this.layout) return;

        // 1. Индексируем координаты биомов
        const biomeCoords = {};
        this.entities.forEach(e => {
            if (e.type === 'Biome' && e.data?.coord) {
                biomeCoords[e.id] = e.data.coord;
            }
        });

        // 2. Группируем локации по родителям (биомам)
        // Map<BiomeID, Array<LocationEntity>>
        const locationsByBiome = {};

        this.entities.forEach(e => {
            if (e.type !== 'Location') return;
            if (!locationsByBiome[e.parent_id]) locationsByBiome[e.parent_id] = [];
            locationsByBiome[e.parent_id].push(e);
        });

        // 3. Распределяем локации внутри тайла
        Object.entries(locationsByBiome).forEach(([parentId, locs]) => {
            const bCoord = biomeCoords[parentId];
            if (!bCoord) return;

            // Сортируем по ID, чтобы порядок был детерминированным (не прыгал)
            locs.sort((a, b) => a.id.localeCompare(b.id));

            const count = locs.length;
            
            locs.forEach((loc, index) => {
                let lx = 0.5, ly = 0.5;

                // --- АЛГОРИТМ РАСКЛАДКИ ---
                if (count === 1) {
                    // Одна локация — строго по центру
                    lx = 0.5; ly = 0.5;
                } else if (count === 2) {
                    // Две — по диагонали
                    if (index === 0) { lx = 0.35; ly = 0.35; }
                    else { lx = 0.65; ly = 0.65; }
                } else {
                    // 3 и более — по кругу
                    const radius = 0.3; // Радиус круга (30% от тайла)
                    const angle = (2 * Math.PI / count) * index - (Math.PI / 2); // -90deg (начинаем сверху)
                    lx = 0.5 + radius * Math.cos(angle);
                    ly = 0.5 + radius * Math.sin(angle);
                }
                // ---------------------------

                const pixelX = (bCoord[0] * CFG.TILE_SIZE) + (lx * CFG.TILE_SIZE);
                const pixelY = (bCoord[1] * CFG.TILE_SIZE) + (ly * CFG.TILE_SIZE);

                this.renderCache.set(loc.id, {
                    x: pixelX,
                    y: pixelY,
                    icon: utils.getIcon(loc) || "📍",
                    created_at: (loc.created_at !== undefined) ? Number(loc.created_at) : 0
                });
            });
        });
    }

    centerCamera() {
        if (!this.layout) return;
        const mapW = this.layout.width * CFG.TILE_SIZE;
        const mapH = this.layout.height * CFG.TILE_SIZE;
        this.camera.x = (this.canvas.width - mapW) / 2;
        this.camera.y = (this.canvas.height - mapH) / 2;
        this.camera.zoom = 1.0;
        this.draw(0);
    }

    draw(epoch = 0, progress = 1.0) {
        if (!this.layout || !this.ctx) return;

        const ctx = this.ctx;
        const W = this.canvas.width;
        const H = this.canvas.height;

        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = '#1e1e1e';
        ctx.fillRect(0, 0, W, H);

        ctx.translate(this.camera.x, this.camera.y);
        ctx.scale(this.camera.zoom, this.camera.zoom);

        this._drawTerrain(ctx);
        this._drawGrid(ctx);
        this._drawLocations(ctx, epoch);
        this._drawEvents(ctx, epoch, progress);
    }

    _drawTerrain(ctx) {
        const { width, height, cells } = this.layout;
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const key = `${x},${y}`;
                const biomeId = cells[key];
                if (!biomeId) continue;

                const px = x * CFG.TILE_SIZE;
                const py = y * CFG.TILE_SIZE;

                let color = CFG.COLORS.default;
                for(const k in CFG.COLORS) {
                    if (biomeId.includes(k)) { color = CFG.COLORS[k]; break; }
                }

                ctx.fillStyle = color;
                ctx.fillRect(px, py, CFG.TILE_SIZE, CFG.TILE_SIZE);
            }
        }
    }

    _drawGrid(ctx) {
        if (this.camera.zoom < 0.5) return;
        const { width, height } = this.layout;
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.lineWidth = 1;
        
        for (let y = 0; y <= height; y++) {
            ctx.beginPath();
            ctx.moveTo(0, y * CFG.TILE_SIZE);
            ctx.lineTo(width * CFG.TILE_SIZE, y * CFG.TILE_SIZE);
            ctx.stroke();
        }
        for (let x = 0; x <= width; x++) {
            ctx.beginPath();
            ctx.moveTo(x * CFG.TILE_SIZE, 0);
            ctx.lineTo(x * CFG.TILE_SIZE, height * CFG.TILE_SIZE);
            ctx.stroke();
        }
    }

    _drawLocations(ctx, epoch) {
        this.renderCache.forEach(item => {
            if (item.created_at > epoch) return;

            // Подложка
            ctx.beginPath();
            ctx.arc(item.x, item.y, CFG.ICON_SIZE/1.3, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,0,0,0.4)';
            ctx.fill();

            // Иконка
            this._drawIcon(ctx, item.icon, item.x, item.y, CFG.ICON_SIZE);
        });
    }

    _drawEvents(ctx, epoch, progress) {
        const epochInt = Math.floor(epoch);
        const events = this.history[epochInt] || [];
        
        const getAnimStyle = (typeRaw) => {
            const t = String(typeRaw).toLowerCase();
            if (t.match(/raid|conflict|war|absorbed_by|raid_start|boss_spawn|attack/)) return { icon: '⚔️', effect: 'pulse', color: 'red' };
            if (t.match(/death|kill|famine|starve|destroy|depleted|perished/)) return { icon: '💀', effect: 'float', color: 'gray' };
            if (t.match(/mov|fled_to|migrat|run|expansion|splintered_from/)) return { icon: '🏃', effect: 'drop', color: 'blue' };
            if (t.match(/new|settl|resource_regrowth|found|discover|believes_in|transform|growth|resource|regrowth/)) return { icon: '✨', effect: 'pop', color: 'gold' };
            if (t.match(/truce|allied_with|joined/)) return { icon: '🤝', effect: 'pop', color: 'white' };
            return { icon: '❗', effect: 'pop', color: 'white' }; 
        };

        events.forEach(evt => {
            const type = evt.data?.event_type || evt.event_type || "unknown";
            const data = evt.data || {};
            
            let targetId = data.location_id; 
            if (!targetId && evt.primary_entity) {
                if (evt.primary_entity.type === 'Location') {
                    targetId = evt.primary_entity.id;
                } 
                else if (['Faction', 'Resource', 'Character'].includes(evt.primary_entity.type)) {
                    const parentEnt = this.entities.find(e => e.id === evt.primary_entity.id);
                    if (parentEnt) targetId = parentEnt.parent_id;
                }
            }

            const pos = this.renderCache.get(targetId);
            if (!pos) return;

            const style = getAnimStyle(type);

            ctx.save();
            ctx.translate(pos.x, pos.y);

            if (style.effect === 'pulse') {
                const s = 1 + Math.sin(progress * Math.PI * 5) * 0.4;
                ctx.scale(s, s);
                this._drawIcon(ctx, style.icon, 0, -20, CFG.EVENT_SIZE);
            } else if (style.effect === 'float') {
                ctx.globalAlpha = Math.max(0.2, 1.0 - progress);
                this._drawIcon(ctx, style.icon, 0, -15 - (progress * 30), CFG.EVENT_SIZE);
            } else if (style.effect === 'drop') {
                const y = -40 * (1 - progress);
                ctx.globalAlpha = Math.max(0.2, progress);
                this._drawIcon(ctx, style.icon, 0, y - 10, CFG.EVENT_SIZE);
            } else {
                const s = Math.min(1, progress * 2);
                ctx.scale(s, s);
                this._drawIcon(ctx, style.icon, 0, -15, CFG.EVENT_SIZE);
            }
            ctx.restore();
        });
    }

    _drawIcon(ctx, icon, x, y, size) {
        ctx.font = `bold ${size}px sans-serif`; 
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(0,0,0,0.8)';
        ctx.strokeText(icon, x, y);
        
        ctx.fillStyle = '#ffffff';
        ctx.fillText(icon, x, y);
    }
}

// === КОНТРОЛЛЕР ===

let renderer = null;
let animationId = null;
let isPlaying = false;
let currentEpoch = 0;
let maxEpoch = 0;

export async function initSimulation() {
    renderer = new WorldRenderer('world-map-canvas');

    document.getElementById('btn-build-world')?.addEventListener('click', handleBuild);
    document.getElementById('btn-run-sim')?.addEventListener('click', handleRun);
    document.getElementById('btn-zoom-reset')?.addEventListener('click', () => renderer.centerCamera());
    
    const slider = document.getElementById('time-slider');
    if (slider) {
        slider.addEventListener('input', (e) => {
            stopAnimation();
            const val = parseInt(e.target.value);
            currentEpoch = val;
            updateLabels(val);
            renderer.draw(val, 1.0);
        });
    }

    await loadBiomeOptions();
}

export function onTabActive() {
    if (!renderer) return;
    const parent = renderer.canvas.parentElement;
    if (parent) {
        renderer.canvas.width = parent.clientWidth;
        renderer.canvas.height = parent.clientHeight;
    }
    renderer.draw(currentEpoch, 1.0);
}

async function handleBuild() {
    updateStatus("Генерация...", true);
    try {
        const w = parseInt(document.getElementById('map-width')?.value || 8);
        const h = parseInt(document.getElementById('map-height')?.value || 6);
        const biomes = getSelectedBiomes();

        await api.post('/api/simulation/build', { width: w, height: h, biome_ids: biomes });
        
        const layoutRes = await api.get('/api/simulation/latest_layout');
        const entRes = await api.get('/api/simulation/latest_entities');
        
        renderer.loadWorld(layoutRes.layout || layoutRes, entRes.entities || []);
        
        currentEpoch = 0;
        maxEpoch = 0;
        updateSlider(0, 0);
        updateStatus("Мир готов", false);

    } catch (e) {
        console.error(e);
        updateStatus("Ошибка: " + e.message, false, true);
    }
}

async function handleRun() {
    if (!renderer.layout) return alert("Сначала создайте мир!");
    
    const epochs = parseInt(document.getElementById('sim-epochs')?.value || 50);
    const btn = document.getElementById('btn-run-sim');
    if(btn) btn.disabled = true;

    try {
        updateStatus("Симуляция...", true);
        await api.post('/api/simulation/run', { epochs });
        
        const logs = await pollLogs(epochs);
        maxEpoch = renderer.loadHistory(logs);
        
        const entRes = await api.get('/api/simulation/latest_entities');
        const newEntities = entRes.entities || [];

        if (newEntities.length > 0) {
            renderer.updateEntities(newEntities);
        }

        updateSlider(maxEpoch, currentEpoch);
        updateStatus("Воспроизведение...", false);
        
        await playMovie();
        updateStatus("Готово", false);

    } catch (e) {
        console.error(e);
        updateStatus("Ошибка симуляции", false, true);
    } finally {
        if(btn) btn.disabled = false;
    }
}

function playMovie() {
    return new Promise(resolve => {
        isPlaying = true;
        let start = null;
        let startEpoch = currentEpoch; 

        function loop(timestamp) {
            if (!isPlaying) { resolve(); return; }
            if (!start) start = timestamp;

            const elapsed = timestamp - start;
            const epochsPassed = elapsed / CFG.ANIMATION_SPEED;
            
            const targetEpochFloat = startEpoch + epochsPassed;
            const targetEpochInt = Math.floor(targetEpochFloat);
            const progress = targetEpochFloat - targetEpochInt;

            if (targetEpochInt > maxEpoch) {
                isPlaying = false;
                currentEpoch = maxEpoch;
                updateSlider(maxEpoch, maxEpoch);
                renderer.draw(maxEpoch, 1.0);
                resolve();
                return;
            }

            if (targetEpochInt !== currentEpoch) {
                currentEpoch = targetEpochInt;
                updateLabels(currentEpoch);
                updateSlider(maxEpoch, currentEpoch);
            }

            renderer.draw(currentEpoch, progress);
            animationId = requestAnimationFrame(loop);
        }
        animationId = requestAnimationFrame(loop);
    });
}

function stopAnimation() {
    isPlaying = false;
    if (animationId) cancelAnimationFrame(animationId);
}

// --- Helpers ---

async function loadBiomeOptions() {
    const container = document.getElementById('biome-selector-container');
    if(!container) return;
    try {
        const data = await api.get('/api/configs/biomes/data');
        container.innerHTML = data.map(b => `
            <div class="form-check form-check-inline m-0 me-2">
                <input class="form-check-input" type="checkbox" value="${b.id}" id="chk-${b.id}" checked>
                <label class="form-check-label small" for="chk-${b.id}">${b.name}</label>
            </div>`).join('');
    } catch(e){}
}

function getSelectedBiomes() {
    return Array.from(document.querySelectorAll('#biome-selector-container input:checked')).map(c => c.value);
}

async function pollLogs(target) {
    let tries = 0;
    while(tries++ < 600) {
        await new Promise(r => setTimeout(r, 1000));
        const res = await api.get('/api/simulation/history_logs');
        const logs = res.logs || [];
        if (logs.length === 0) continue;

        let max = 0;
        logs.forEach(l => {
            try { 
                const evt = (typeof l === 'string') ? JSON.parse(l) : l;
                let age = 0;
                if(evt.created_at) age = evt.created_at;
                else if(evt.age) age = evt.age;
                else if(evt.data && evt.data.age) age = evt.data.age;
                if(age > max) max = age; 
            } catch(e){}
        });
        
        updateStatus(`Эпоха: ${max}/${target}`, true);
        if(max >= target) return logs;
    }
    return [];
}

function updateStatus(msg, loading, error) {
    const el = document.getElementById('sim-status');
    if(!el) return;
    el.className = `badge ${error ? 'bg-danger' : 'bg-secondary'}`;
    el.innerHTML = loading ? `<span class="spinner-border spinner-border-sm"></span> ${msg}` : msg;
}

function updateSlider(max, val) {
    const s = document.getElementById('time-slider');
    if(s) { s.max = max; s.value = val; s.disabled = false; }
}

function updateLabels(val) {
    const l = document.getElementById('lbl-age');
    if(l) l.innerText = val;
    renderLogsText(val);
}

function renderLogsText(epoch) {
    const el = document.getElementById('sim-logs');
    if(!el || !renderer.history[epoch]) return;
    
    el.innerHTML = `<div class="sticky-top bg-light p-2 border-bottom fw-bold">Эпоха ${epoch}</div>` + 
    renderer.history[epoch].map(evt => {
        // === ИСПРАВЛЕНИЕ: Приоритет данных из data ===
        const type = evt.data?.event_type || evt.event_type || "Event";
        const summary = evt.data?.summary || evt.summary || evt.name || "...";
        
        // Определение цвета текста для красоты
        let colorClass = "text-dark";
        const t = type.toLowerCase();
        
        if (t.includes('war') || t.includes('conflict') || t.includes('raid')) {
            colorClass = "text-danger fw-bold"; // Красный
        } else if (t.includes('new') || t.includes('discover') || t.includes('growth')) {
            colorClass = "text-success"; // Зеленый
        } else if (t.includes('death') || t.includes('depleted')) {
            colorClass = "text-secondary"; // Серый
        }
        
        return `
        <div class="p-1 mb-1 border-bottom small">
            <span class="${colorClass}">${type}</span>: ${summary}
        </div>`;
    }).join('');
}