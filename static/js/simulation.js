import { api } from './api.js';
import { utils } from './utils.js';

// === КОНФИГУРАЦИЯ ===
const CFG = {
    TILE_SIZE: 64,
    ICON_SIZE: 20,       // Размер иконки локации
    EVENT_SIZE: 24,      // Размер иконки события
    ANIMATION_SPEED: 800, // мс на эпоху
    COLORS: {
        'plain': '#4ade80', 'forest': '#166534', 'desert': '#fde047',
        'mountain': '#57534e', 'coast': '#3b82f6', 'swamp': '#4d7c0f',
        'tundra': '#cffafe', 'wasteland': '#78350f', 'default': '#2b2b2b'
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
        
        // Map<EntityID, {x, y, icon, created_at}>
        this.renderCache = new Map(); 

        this.camera = { x: 0, y: 0, zoom: 1.0 };
        this.isDragging = false;
        this.lastMouse = { x: 0, y: 0 };

        this._setupInput();
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

    loadWorld(layout, entities) {
        this.layout = layout;
        this.updateEntities(entities);
        this.centerCamera();
    }

    // === ГЛАВНЫЙ МЕТОД ПАРСИНГА ИСТОРИИ ===
    loadHistory(historyLogs) {
        this.history = {};
        let maxAge = 0;
        let debugOnce = false;
        
        historyLogs.forEach(line => {
            try {
                const evt = (typeof line === 'string') ? JSON.parse(line) : line;
                
                // ОТЛАДКА: Выводим структуру первого события в консоль
                if (!debugOnce) {
                    console.log("🔍 Sample Event Structure:", evt);
                    debugOnce = true;
                }

                // === ИСПРАВЛЕНИЕ ЗДЕСЬ ===
                // 1. Проверяем created_at (стандарт Pydantic)
                // 2. Проверяем age (если есть в корне)
                // 3. Проверяем data.age (если вложено)
                let age = 0;
                if (evt.created_at !== undefined) age = evt.created_at;
                else if (evt.age !== undefined) age = evt.age;
                else if (evt.data?.age !== undefined) age = evt.data.age;
                
                // Приводим к числу на всякий случай
                age = Number(age);

                if (age > maxAge) maxAge = age;
                
                if (!this.history[age]) this.history[age] = [];
                this.history[age].push(evt);
            } catch (e) {
                console.error("Parse error:", e);
            }
        });
        
        console.log(`✅ History loaded. Max Age found: ${maxAge}`);
        return maxAge;
    }

    updateEntities(newEntities) {
        this.entities = newEntities || [];
        this._rebuildCache();
    }

    _rebuildCache() {
        this.renderCache.clear();
        
        console.group("🛠️ Debug: Rebuilding Cache");
        
        // 1. ПРОВЕРКА СПИСКА
        if (!this.entities || this.entities.length === 0) {
            console.warn("⚠️ Entities list is EMPTY! Check handleBuild/handleRun parsing.");
            console.groupEnd();
            return;
        }

        console.log(`Total entities to process: ${this.entities.length}`);
        
        // 2. ВЫВОД ПРИМЕРА (Первый элемент)
        console.log("🔍 First entity structure:", this.entities[0]);

        // 3. СБОР КООРДИНАТ БИОМОВ
        const biomeCoords = {};
        const stats = { biomes: 0, locations: 0, others: 0 };
        
        this.entities.forEach(e => {
            // Приводим тип к строке и нижнему регистру для сравнения
            const type = String(e.type || "unknown").toLowerCase();
            
            if (type === 'biome') {
                // Ищем координаты в data.coord
                if (e.data && e.data.coord) {
                    biomeCoords[e.id] = e.data.coord;
                    stats.biomes++;
                } else {
                    console.warn(`⚠️ Biome ${e.id} missing data.coord`, e);
                }
            } else if (type === 'location') {
                stats.locations++;
            } else {
                stats.others++;
            }
        });

        console.log(`Stats: ${stats.biomes} biomes (with coords), ${stats.locations} locations found.`);

        if (stats.biomes === 0) {
            console.error("❌ No biomes with coordinates found! Map will be empty.");
            console.groupEnd();
            return;
        }

        // 4. КЭШИРОВАНИЕ ЛОКАЦИЙ
        let cachedCount = 0;
        
        this.entities.forEach(e => {
            const type = String(e.type || "").toLowerCase();
            if (type !== 'location') return;

            const bCoord = biomeCoords[e.parent_id];
            
            if (!bCoord) {
                // Это частая ошибка: локация ссылается на биом, которого нет или у которого нет координат
                // console.debug(`Skipping location ${e.name}: parent ${e.parent_id} coords not found`);
                return;
            }

            // Координаты внутри тайла (local_coord)
            const local = e.data?.local_coord || [0.5, 0.5];
            
            // Расчет позиции на экране
            const pixelX = (bCoord[0] * CFG.TILE_SIZE) + (local[0] * CFG.TILE_SIZE);
            const pixelY = (bCoord[1] * CFG.TILE_SIZE) + (local[1] * CFG.TILE_SIZE);

            this.renderCache.set(e.id, {
                x: pixelX,
                y: pixelY,
                icon: utils.getIcon(e) || "📍",
                created_at: (e.created_at !== undefined) ? Number(e.created_at) : 0
            });
            cachedCount++;
        });

        console.log(`✅ Successfully cached ${cachedCount} locations.`);
        console.groupEnd();
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
        this._drawGrid(ctx); // Рисуем сетку для наглядности
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

    // Вспомогательная сетка (тонкие линии)
    _drawGrid(ctx) {
        if (this.camera.zoom < 0.5) return; // Оптимизация
        const { width, height } = this.layout;
        
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.lineWidth = 1;
        
        // Внешние границы тайлов
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
            // Если локация еще не родилась — пропускаем
            if (item.created_at > epoch) return;

            // Рисуем полупрозрачную подложку
            ctx.beginPath();
            ctx.arc(item.x, item.y, CFG.ICON_SIZE / 1.5, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,0,0,0.5)'; // Темная подложка
            ctx.fill();
            
            // Если это новая локация (текущей эпохи), можно подсветить
            if (item.created_at === epoch && epoch > 0) {
                 ctx.strokeStyle = '#ffff00';
                 ctx.lineWidth = 2;
                 ctx.stroke();
            }

            // Рисуем иконку
            this._drawIcon(ctx, item.icon, item.x, item.y);
        });
    }

    // TODO: проверить парсинг
    _drawEvents(ctx, epoch, progress) {
        const events = this.history[epoch] || [];
        
        const getAnimStyle = (type) => {
            const t = String(type).toLowerCase(); // Приводим к строке и нижнему регистру

            // 1. ВОЙНА (Красные мечи)
            if (t.match(/raid|conflict|war|siege|battle|fight|attack/)) 
                return { icon: '⚔️', effect: 'pulse', color: 'red' };
            
            // 2. СМЕРТЬ И РАЗРУШЕНИЕ (Серый череп) + ИСТОЩЕНИЕ РЕСУРСОВ
            if (t.match(/death|kill|execut|starve|destroy|depleted|perished/)) 
                return { icon: '💀', effect: 'float', color: 'gray' };
            
            // 3. ДВИЖЕНИЕ (Синий бегун)
            if (t.match(/mov|fled|migrat|run|exile|wander/)) 
                return { icon: '🏃', effect: 'drop', color: 'blue' };
            
            // 4. ПОЗИТИВ / РОСТ (Золотая искра)
            if (t.match(/new|settl|birth|found|discover|construct|transform|growth|resource/)) 
                return { icon: '✨', effect: 'pop', color: 'gold' };
            
            // 5. ДИПЛОМАТИЯ (Белое рукопожатие)
            if (t.match(/truce|alliance|peace/)) 
                return { icon: '🤝', effect: 'pop', color: 'white' };
            
            // Фоллбэк (если тип не распознан)
            return { icon: '❗', effect: 'pop', color: 'white' }; 
        };

        events.forEach(evt => {
            // ИЗВЛЕЧЕНИЕ ТИПА: Сначала смотрим в data.event_type (самый точный), потом fallback
            const type = evt.data?.event_type || evt.event_type || "unknown";
            const data = evt.data || {};
            
            // Логика поиска координат (без изменений)
            let targetId = data.location_id;
            if (!targetId && evt.primary_entity) {
                if (evt.primary_entity.type === 'Location') {
                    targetId = evt.primary_entity.id;
                } else if (evt.primary_entity.type === 'Faction') {
                    const fac = this.entities.find(e => e.id === evt.primary_entity.id);
                    if (fac) targetId = fac.parent_id;
                }
            }

            const pos = this.renderCache.get(targetId);
            if (!pos) return;

            const style = getAnimStyle(type);

            ctx.save();
            ctx.translate(pos.x, pos.y);

            // Отрисовка эффектов (без изменений)
            if (style.effect === 'pulse') {
                const s = 1 + Math.sin(progress * Math.PI * 5) * 0.4;
                ctx.scale(s, s);
                this._drawIcon(ctx, style.icon, 0, -20);
            } else if (style.effect === 'float') {
                ctx.globalAlpha = 1.0 - progress;
                this._drawIcon(ctx, style.icon, 0, -15 - (progress * 30));
            } else if (style.effect === 'drop') {
                const y = -40 * (1 - progress);
                ctx.globalAlpha = progress;
                this._drawIcon(ctx, style.icon, 0, y - 10);
            } else {
                const s = Math.min(1, progress * 2);
                ctx.scale(s, s);
                this._drawIcon(ctx, style.icon, 0, -15);
            }
            ctx.restore();
        });
    }

    _drawIcon(ctx, icon, x, y) {
        // Настройка шрифта
        ctx.font = `bold ${CFG.ICON_SIZE}px sans-serif`; // Используем sans-serif для эмодзи
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // 1. Рисуем жирную черную обводку
        ctx.lineWidth = 4;
        ctx.lineJoin = 'round';
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
        ctx.strokeText(icon, x, y);
        
        // 2. Рисуем саму иконку белым (хотя эмодзи имеют свой цвет, 
        // fillText важен для некоторых символов)
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
        
        // ВАЖНО: Парсим историю и получаем реальный Max Age
        maxEpoch = renderer.loadHistory(logs);
        
        // Обновляем сущности (чтобы увидеть новые города)
        const entRes = await api.get('/api/simulation/latest_entities');
        renderer.updateEntities(entRes.entities || []);

        // Ставим слайдер в конец, но запускаем анимацию с 0 (или текущей)
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
                // ИСПРАВЛЕНИЕ ПАРСИНГА ДЛЯ СТАТУС БАРА
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
    console.warn("Polling timeout");
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