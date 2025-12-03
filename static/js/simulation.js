import { api } from './api.js';
import { utils } from './utils.js';


// Цветовая схема для биомов (Hex коды)
const BIOME_COLORS = {
    'plain': '#4ade80',    // Светло-зеленый
    'forest': '#166534',   // Темно-зеленый
    'desert': '#fde047',   // Песочный
    'mountain': '#57534e', // Серый камень
    'coast': '#3b82f6',    // Синий
    'swamp': '#4d7c0f',    // Болотный
    'tundra': '#cffafe',      // Ледяной
    'wasteland': '#78350f' // Коричневый
};

// Запасной цвет, если биом не найден
const DEFAULT_COLOR = '#2b2b2b';

// Глобальные переменные состояния
let worldHistory = []; 
let worldLayout = null; 
let baseEntities = []; 
let maxAge = 0;
let currentEpoch = 0;

// Камера
const camera = {
    x: 0,
    y: 0,
    zoom: 1.0,
    isDragging: false,
    lastX: 0,
    lastY: 0
};

const TILE_SIZE = 64; 

export async function initSimulation() {
    console.log("Init simulation...");

    const btnBuild = document.getElementById('btn-build-world');
    const btnRun = document.getElementById('btn-run-sim');
    const timeSlider = document.getElementById('time-slider');
    
    // Привязываем кнопки
    if (btnBuild) btnBuild.addEventListener('click', buildWorld);
    if (btnRun) btnRun.addEventListener('click', runSimulation);

    // Привязываем слайдер (Событие input срабатывает при перетаскивании)
    if (timeSlider) {
        // Сброс при старте
        timeSlider.disabled = true;
        timeSlider.value = 0;
        
        timeSlider.addEventListener('input', (e) => {
            // Превращаем строку в число
            const epoch = parseInt(e.target.value, 10);
            
            // Обновляем визуализацию
            renderStateAtEpoch(epoch);
            
            // Обновляем цифру рядом со слайдером
            const lbl = document.getElementById('lbl-age');
            if(lbl) lbl.innerText = epoch;
        });
    }

    // Привязка зума и канваса
    const canvas = document.getElementById('world-map-canvas');
    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');
    const btnZoomReset = document.getElementById('btn-zoom-reset');

    if (canvas) {
        setupCanvasInteractions(canvas);
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);
    }
    
    if (btnZoomIn) btnZoomIn.addEventListener('click', () => changeZoom(1.2));
    if (btnZoomOut) btnZoomOut.addEventListener('click', () => changeZoom(0.8));
    if (btnZoomReset) btnZoomReset.addEventListener('click', resetCamera);

    await loadBiomeOptions();
}

// --- CANVAS INTERACTION (ZOOM & PAN) ---

function resizeCanvas() {
    const cvs = document.getElementById('world-map-canvas');
    if (!cvs) return;
    
    // Канвас берет размер родителя (.card-body)
    const parent = cvs.parentElement;
    cvs.width = parent.clientWidth;
    cvs.height = parent.clientHeight;
    
    // Перерисовываем, если есть данные
    if (worldLayout) drawWorld(currentEpoch);
}

export async function loadSimulationData() {
    if (worldLayout) {
        renderStateAtEpoch(currentEpoch);
    }
}

function setupCanvasInteractions(cvs) {
    // Зум колесиком
    cvs.addEventListener('wheel', (e) => {
        e.preventDefault();
        const factor = e.deltaY > 0 ? 0.9 : 1.1;
        changeZoom(factor);
    });

    // Панорамирование (Drag)
    cvs.addEventListener('mousedown', (e) => {
        camera.isDragging = true;
        camera.lastX = e.offsetX;
        camera.lastY = e.offsetY;
        cvs.style.cursor = 'grabbing';
    });

    cvs.addEventListener('mousemove', (e) => {
        if (!camera.isDragging) return;
        const dx = e.offsetX - camera.lastX;
        const dy = e.offsetY - camera.lastY;
        
        camera.x += dx;
        camera.y += dy;
        
        camera.lastX = e.offsetX;
        camera.lastY = e.offsetY;
        
        drawWorld(currentEpoch);
    });

    const stopDrag = () => {
        camera.isDragging = false;
        cvs.style.cursor = 'grab';
    };

    cvs.addEventListener('mouseup', stopDrag);
    cvs.addEventListener('mouseleave', stopDrag);
}

function changeZoom(factor) {
    const newZoom = camera.zoom * factor;
    // Ограничение зума
    if (newZoom > 0.1 && newZoom < 5.0) {
        camera.zoom = newZoom;
        drawWorld(currentEpoch);
    }
}

function resetCamera() {
    if (!worldLayout) return;
    const cvs = document.getElementById('world-map-canvas');
    
    // Центрируем карту
    const mapW = worldLayout.width * TILE_SIZE;
    const mapH = worldLayout.height * TILE_SIZE;
    
    camera.zoom = 1.0;
    camera.x = (cvs.width - mapW) / 2;
    camera.y = (cvs.height - mapH) / 2;
    
    drawWorld(currentEpoch);
}

// --- DATA & LOGIC ---

async function loadBiomeOptions() {
    const container = document.getElementById('biome-selector-container');
    try {
        const biomes = await api.get('/api/configs/biomes/data');
        if (!biomes || biomes.length === 0) {
            container.innerHTML = '<span class="text-muted small">Биомы не найдены</span>';
            return;
        }
        container.innerHTML = '';
        biomes.forEach(b => {
            const div = document.createElement('div');
            div.className = 'form-check form-check-inline m-0 me-2';
            const icon = b.icon || utils.getIcon({type: 'Biome', definition_id: b.id});
            div.innerHTML = `
                <input class="form-check-input" type="checkbox" value="${b.id}" id="chk-${b.id}">
                <label class="form-check-label small" for="chk-${b.id}" title="${b.name}">
                    ${icon} ${b.name || b.id}
                </label>
            `;
            container.appendChild(div);
        });
    } catch (e) {
        console.error("Biomes load error:", e);
    }
}

function renderLegend() {
    const legend = document.getElementById('map-legend');
    legend.innerHTML = `
        <span class="d-flex align-items-center gap-1"><span style="color:#e74c3c">⚔️</span> Война</span>
        <span class="d-flex align-items-center gap-1"><span style="color:#2ecc71">🌲</span> Природа</span>
        <span class="d-flex align-items-center gap-1"><span style="color:#f1c40f">💰</span> Ресурс</span>
        <span class="d-flex align-items-center gap-1"><span style="color:#9b59b6">💀</span> Смерть</span>
    `;
}

async function buildWorld() {
    updateStatus("Генерация...", true);
    
    const wInput = document.getElementById('map-width');
    const hInput = document.getElementById('map-height');
    const width = wInput ? parseInt(wInput.value) || 8 : 8;
    const height = hInput ? parseInt(hInput.value) || 6 : 6;

    // Собираем биомы
    const selectedBiomes = [];
    document.querySelectorAll('#biome-selector-container input:checked').forEach(chk => {
        selectedBiomes.push(chk.value);
    });

    try {
        await api.post('/api/simulation/build', { 
            width, height, 
            biome_ids: selectedBiomes.length ? selectedBiomes : null
        });
        
        // Получаем данные
        const layoutRes = await api.get('/api/simulation/latest_layout');
        const entRes = await api.get('/api/simulation/latest_entities');
        
        worldLayout = layoutRes.layout || layoutRes;
        baseEntities = entRes.entities || [];
        
        // Сброс
        worldHistory = [];
        maxAge = 0;
        currentEpoch = 0;
        
        updateSlider(0);
        resetCamera(); // Центрируем камеру
        
        updateStatus(`Мир построен (${width}x${height})`, false);
    } catch (e) {
        updateStatus(`Ошибка: ${e.message}`, false, true);
    }
}

async function runSimulation() {
    if (!worldLayout) {
        showToast("Сначала постройте мир!", "error");
        return;
    }

    const epochsInput = document.getElementById('sim-epochs');
    const targetEpochs = epochsInput ? (parseInt(epochsInput.value) || 50) : 50;
    const btnRun = document.getElementById('btn-run-sim');
    const statusBadge = document.getElementById('sim-status');

    if(btnRun) btnRun.disabled = true;
    
    try {
        // 1. Отправляем команду на старт
        if(statusBadge) statusBadge.innerText = "Запуск...";
        await api.post('/api/simulation/run', { epochs: targetEpochs });
        
        // 2. ЗАПУСКАЕМ ПОЛЛИНГ (ОПРОС)
        // Мы будем опрашивать сервер, пока не получим все эпохи
        // или пока симуляция не остановится.
        const logs = await pollSimulationLogs(targetEpochs, (current, target) => {
            if(statusBadge) statusBadge.innerText = `Симуляция: ${current}/${target}`;
        });
        
        // 3. Данные получены, парсим их
        parseHistory(logs);
        
        // 4. Настройка слайдера
        const slider = document.getElementById('time-slider');
        if(slider) {
            slider.min = 0;
            slider.max = maxAge;
            slider.value = 0;
            slider.disabled = false;
        }
        
        // 5. Воспроизведение
        if(statusBadge) statusBadge.innerText = "Воспроизведение...";
        await playAnimation();
        
        // 6. Финал
        if(statusBadge) statusBadge.innerText = "Готово";
        showToast(`Симуляция завершена! (Эпох: ${maxAge})`);

    } catch (e) {
        console.error(e);
        if(statusBadge) statusBadge.innerText = "Ошибка";
        showToast(`Ошибка: ${e.message}`, "error");
    } finally {
        if(btnRun) btnRun.disabled = false;
    }
}

// === ДОБАВЬТЕ ЭТУ НОВУЮ ФУНКЦИЮ В КОНЕЦ ФАЙЛА ===

/**
 * Опрашивает сервер каждые 1 сек, проверяя логи.
 * Завершается, когда достигнута целевая эпоха ИЛИ когда развитие мира остановилось.
 */
/**
 * Опрашивает сервер, проверяя логи.
 * Завершается, когда достигнута целевая эпоха ИЛИ когда развитие мира остановилось.
 */
async function pollSimulationLogs(targetEpoch, onProgress) {
    let attempts = 0;
    const maxAttempts = 1200; // 20 минут максимум
    let lastMaxAge = -1;
    let sameAgeCount = 0; 
    
    while (attempts < maxAttempts) {
        // Ждем 1 секунду (можно уменьшить до 500мс для отзывчивости)
        await new Promise(r => setTimeout(r, 1000));
        
        try {
            const logRes = await api.get('/api/simulation/history_logs');
            // Бэкенд возвращает массив строк, а не объектов!
            const rawLogs = logRes.logs || [];
            
            let currentMax = 0;

            // --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
            rawLogs.forEach(lineStr => {
                try {
                    // Обязательно парсим строку в объект
                    const evt = JSON.parse(lineStr);
                    
                    // Ищем возраст в корне или внутри data
                    const age = (evt.age !== undefined) ? evt.age : (evt.data?.age || 0);
                    
                    if (age > currentMax) currentMax = age;
                } catch (e) {
                    // Игнорируем битые строки JSON, если они есть
                }
            });
            // -------------------------

            // Сообщаем о прогрессе
            if (onProgress) onProgress(currentMax, targetEpoch);

            // УСЛОВИЕ 1: Успех (достигли или перегнали цель)
            if (currentMax >= targetEpoch) {
                return rawLogs;
            }

            // УСЛОВИЕ 2: Остановка (мир умер или перестал меняться)
            if (currentMax > 0 && currentMax === lastMaxAge) {
                sameAgeCount++;
                // Если 4 секунды (4 цикла) эпоха не меняется — считаем, что конец
                if (sameAgeCount >= 4) {
                    console.log(`Симуляция остановилась на эпохе ${currentMax}`);
                    return rawLogs;
                }
            } else {
                sameAgeCount = 0;
            }

            lastMaxAge = currentMax;
            
        } catch (err) {
            console.warn("Ошибка опроса:", err);
            // Не выходим, пробуем еще раз (сеть могла мигнуть)
        }

        attempts++;
    }

    throw new Error("Тайм-аут: симуляция заняла слишком много времени.");
}

// === 3. ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ TOAST ===
function showToast(message, type = 'success') {
    const toastEl = document.getElementById('liveToast');
    if (!toastEl) return;

    // Меняем текст внутри
    const body = toastEl.querySelector('.toast-body');
    if(body) body.innerText = message;

    // Меняем цвет заголовка (опционально)
    const header = toastEl.querySelector('.toast-header');
    if (header) {
        header.className = type === 'error' 
            ? 'toast-header bg-danger text-white' 
            : 'toast-header bg-success text-white';
    }

    // Инициализируем и показываем через Bootstrap API
    // (Убедитесь, что bootstrap.bundle.min.js подключен в index.html)
    const toast = new bootstrap.Toast(toastEl);
    toast.show();
}

function parseHistory(logs) {
    worldHistory = [];
    maxAge = 0;
    const eventsByAge = {};

    logs.forEach(line => {
        try {
            const evt = JSON.parse(line);
            // Берем возраст из корня или из data
            const age = evt.age || (evt.data && evt.data.age) || 0;
            if (age > maxAge) maxAge = age;
            
            if (!eventsByAge[age]) eventsByAge[age] = [];
            eventsByAge[age].push(evt);
        } catch (e) {}
    });

    worldHistory = eventsByAge;
}

function updateStatus(msg, isLoading, isError=false) {
    const el = document.getElementById('sim-status');
    if(!el) return;
    el.innerHTML = isLoading ? `<span class="spinner-border spinner-border-sm"></span> ${msg}` : msg;
    if (isError) {
        el.classList.remove('bg-secondary', 'text-white');
        el.classList.add('bg-danger', 'text-white');
    } else {
        el.classList.remove('bg-danger');
        el.classList.add('bg-secondary');
    }
}

function updateSlider(val) {
    const s = document.getElementById('time-slider');
    const l = document.getElementById('lbl-age');
    if(s) { s.value = val; s.max = val; }
    if(l) l.innerText = val;
}

// --- ВИЗУАЛИЗАЦИЯ (Time Machine) ---

function renderStateAtEpoch(epoch) {
    const l = document.getElementById('lbl-age');
    if(l) l.innerText = epoch;
    
    currentEpoch = epoch;
    drawWorld(epoch);
    renderLogsUntil(epoch);
}

function renderLogsUntil(epoch) {
    const container = document.getElementById('sim-logs');
    if (!container) return;
    
    // Используем epoch, переданный в аргументе
    const events = worldHistory[epoch] || [];
    
    let html = events.map(evt => {
        // Защита от отсутствующих полей
        const data = evt.data || {};
        const type = evt.event_type || data.event_type || 'Event';
        const summary = evt.summary || data.summary || evt.name || '...';
        
        // Визуальное оформление
        let badgeColor = "bg-secondary";
        let icon = "📌";
        
        const typeStr = String(type);
        if (typeStr.includes("conflict") || typeStr.includes("raid")) { badgeColor = "bg-danger"; icon = "⚔️"; }
        else if (typeStr.includes("death") || typeStr.includes("depleted")) { badgeColor = "bg-dark"; icon = "💀"; }
        else if (typeStr.includes("discovery") || typeStr.includes("regrowth")) { badgeColor = "bg-success"; icon = "🌱"; }
        else if (typeStr.includes("transform") || typeStr.includes("expand")) { badgeColor = "bg-warning text-dark"; icon = "✨"; }

        return `
            <div class="p-2 mb-1 border rounded bg-white shadow-sm d-flex gap-2 align-items-start">
                <span class="badge ${badgeColor}">${icon}</span>
                <div>
                    <div class="small fw-bold text-uppercase text-muted" style="font-size: 0.65rem">${type}</div>
                    <div class="small" style="line-height: 1.2">${summary}</div>
                </div>
            </div>
        `;
    }).join('');

    if (events.length === 0) html = `<div class="text-muted small text-center mt-2">Нет событий в эту эпоху</div>`;

    // Здесь тоже используем переменную epoch
    container.innerHTML = `<div class="sticky-top bg-light border-bottom p-2 mb-2 fw-bold text-primary">Эпоха ${epoch}</div>` + html;
}

// --- ОТРИСОВКА КАРТЫ С КАМЕРОЙ ---

function drawWorld(epoch) {
    const cvs = document.getElementById('world-map-canvas');
    if (!cvs || !worldLayout) return;
    const ctx = cvs.getContext('2d');

    // 1. Очистка (заливаем фоном пустоты)
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, cvs.width, cvs.height);
    
    // 2. Применение камеры
    ctx.save();
    ctx.translate(camera.x, camera.y);
    ctx.scale(camera.zoom, camera.zoom);

    // Подготовка данных
    const locMap = {}; 
    const contentMap = {}; 
    
    baseEntities.forEach(e => {
        if (e.type === 'Location') {
            locMap[e.id] = e;
            contentMap[e.id] = [];
        }
    });
    
    baseEntities.forEach(e => {
        if (e.parent_id && locMap[e.parent_id]) {
            contentMap[e.parent_id].push(e);
        }
    });

    // Отрисовка тайлов
    for (let y = 0; y < worldLayout.height; y++) {
        for (let x = 0; x < worldLayout.width; x++) {
            const px = x * TILE_SIZE;
            const py = y * TILE_SIZE;
            const key = `${x},${y}`;
            const biomeId = worldLayout.cells[key];

            if (!biomeId) continue;

            // Биом
            ctx.fillStyle = utils.getColor(biomeId, 1.0);
            ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.lineWidth = 1;
            ctx.strokeRect(px, py, TILE_SIZE, TILE_SIZE);

            // Локации в этом биоме
            const biomeEnt = baseEntities.find(e => 
                e.type === 'Biome' && 
                e.data?.coord && 
                e.data.coord[0] === x && 
                e.data.coord[1] === y
            );

            if (biomeEnt) {
                const locations = baseEntities.filter(e => e.parent_id === biomeEnt.id && e.type === 'Location');
                
                locations.forEach(loc => {
                    const slot = loc.data?.slot_index || 0;
                    const pos = getSlotPosition(slot, px, py);
                    
                    // Сама локация
                    ctx.font = '24px serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.shadowColor = "rgba(0,0,0,0.5)";
                    ctx.shadowBlur = 4;
                    ctx.fillText(utils.getIcon(loc), pos.x, pos.y);
                    ctx.shadowBlur = 0;
                    
                    // Дети (Фракции, ресурсы)
                    const children = contentMap[loc.id] || [];
                    if (children.length > 0) {
                        drawChildrenSmall(ctx, children, pos.x, pos.y);
                    }
                });
            }
        }
    }
    
    ctx.restore();
}

function drawTerrain(ctx) {
    if (!worldLayout || !ctx) return;

    for (let y = 0; y < worldLayout.height; y++) {
        for (let x = 0; x < worldLayout.width; x++) {
            const key = `${x},${y}`;
            const biomeId = worldLayout.cells[key]; 
            
            // Определяем цвет
            let color = DEFAULT_COLOR;
            if (biomeId) {
                // Ищем совпадение ключа биома с нашей палитрой
                const type = Object.keys(BIOME_COLORS).find(k => biomeId.includes(k));
                if (type) color = BIOME_COLORS[type];
            }

            const px = x * TILE_SIZE;
            const py = y * TILE_SIZE;

            // Рисуем тайл
            ctx.fillStyle = color;
            ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE);
            
            // Рисуем легкую сетку
            ctx.strokeStyle = 'rgba(0,0,0,0.1)';
            ctx.lineWidth = 1;
            ctx.strokeRect(px, py, TILE_SIZE, TILE_SIZE);
        }
    }
}

// В drawWorld добавь параметр progress (от 0.0 до 1.0)
// epoch - текущая базовая эпоха (откуда едем)
// nextEpoch - следующая (куда едем)
function drawWorldSmooth(epoch, progress) {
    const cvs = document.getElementById('world-map-canvas');
    if (!cvs || !worldLayout) return;

    // === ВОТ ЗДЕСЬ БЫЛА ОШИБКА ===
    // Мы должны получить контекст прямо тут
    const ctx = cvs.getContext('2d'); 
    // =============================

    // 1. Очистка и камера
    ctx.save();
    
    // Сброс трансформации перед очисткой (важно!)
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#2b2b2b';
    ctx.fillRect(0, 0, cvs.width, cvs.height);
    
    // Применяем зум/панорамирование
    ctx.translate(camera.x, camera.y);
    ctx.scale(camera.zoom, camera.zoom);

    // 2. Рисуем землю (передаем ctx)
    drawTerrain(ctx);

    // 3. Рисуем СТАТИЧНЫЕ объекты (Города, Данжи)
    baseEntities.forEach(ent => {
        if (ent.type === 'Location' && ent.parent_id) {
            const biome = baseEntities.find(b => b.id === ent.parent_id);
            if (biome && biome.data && biome.data.coord) {
                const [bx, by] = biome.data.coord;
                const px = bx * TILE_SIZE + TILE_SIZE / 2;
                const py = by * TILE_SIZE + TILE_SIZE / 2;
                
                ctx.font = '24px serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = '#fff';
                ctx.shadowColor = "rgba(0,0,0,0.8)";
                ctx.shadowBlur = 4;
                // Используем иконку или заглушку
                ctx.fillText(utils.getIcon ? utils.getIcon(ent) : '🏘️', px, py);
                ctx.shadowBlur = 0;
            }
        }
    });

    // 4. Рисуем ДИНАМИЧЕСКИЕ СОБЫТИЯ
    // Используем Math.floor(epoch), потому что массив событий дискретный
    // А progress используем только для визуальных эффектов
    const currentEpochInt = Math.floor(epoch); 
    const events = worldHistory[currentEpochInt] || [];
    
    events.forEach((evt) => {
        // Логика поиска координат события
        const locId = evt.data?.location_id || evt.location_id;
        let targetEnt = null;
        
        if (locId) {
            targetEnt = baseEntities.find(e => e.id === locId);
        } else if (evt.data?.location_name) {
            targetEnt = baseEntities.find(e => e.name === evt.data.location_name);
        }

        if (targetEnt && targetEnt.parent_id) {
            const biome = baseEntities.find(b => b.id === targetEnt.parent_id);
            if (biome && biome.data?.coord) {
                const [bx, by] = biome.data.coord;
                
                // Анимация подпрыгивания (синусоида)
                const bounce = Math.sin(progress * Math.PI) * 15; 
                
                const px = bx * TILE_SIZE + TILE_SIZE / 2;
                // Смещаем иконку события выше города и добавляем прыжок
                const py = (by * TILE_SIZE + TILE_SIZE / 2) - 20 - bounce;

                let icon = "✨";
                const type = String(evt.event_type || "");
                if (type.includes('raid') || type.includes('conflict')) icon = "⚔️";
                if (type.includes('death')) icon = "💀";
                
                ctx.font = '24px serif';
                ctx.fillStyle = '#fff'; // Белый цвет лучше виден на цветной карте
                ctx.shadowColor = "#000";
                ctx.shadowBlur = 3;
                ctx.fillText(icon, px, py);
                ctx.shadowBlur = 0;
            }
        }
    });

    ctx.restore();
}

function getSlotPosition(slotIndex, cellX, cellY) {
    const offset = TILE_SIZE / 4;
    const cx = cellX + TILE_SIZE / 2;
    const cy = cellY + TILE_SIZE / 2;

    switch(slotIndex) {
        case 0: return {x: cx, y: cy};
        case 1: return {x: cx - offset, y: cy - offset};
        case 2: return {x: cx + offset, y: cy + offset};
        case 3: return {x: cx + offset, y: cy - offset};
        case 4: return {x: cx - offset, y: cy + offset};
        default: return {x: cx, y: cy};
    }
}

function drawChildrenSmall(ctx, children, parentX, parentY) {
    ctx.font = '12px serif';
    // Рисуем полукругом или просто рядом
    children.slice(0, 3).forEach((child, i) => {
        const icon = utils.getIcon(child);
        // Смещение иконок детей, чтобы не перекрывали локацию
        const offsetX = (i - 1) * 12;
        const offsetY = 14; 
        ctx.fillText(icon, parentX + offsetX, parentY + offsetY);
    });
}

function playAnimation() {
    return new Promise(resolve => {
        const btnRun = document.getElementById('btn-run-sim');
        if (btnRun) btnRun.disabled = true;

        let startTimestamp = null;
        const durationPerEpoch = 600; // 600 мс на одну эпоху (чуть медленнее, чтобы разглядеть)
        
        function step(timestamp) {
            if (!startTimestamp) startTimestamp = timestamp;
            const elapsed = timestamp - startTimestamp;
            
            // Вычисляем текущий прогресс (float)
            const totalProgress = elapsed / durationPerEpoch;
            const currentEpochIndex = Math.floor(totalProgress);
            
            // Если дошли до конца
            if (currentEpochIndex > maxAge) {
                renderStateAtEpoch(maxAge); // Финальная отрисовка
                if (btnRun) btnRun.disabled = false;
                resolve();
                return;
            }

            // Прогресс внутри текущей эпохи (0.0 -> 1.0)
            const epochProgress = totalProgress - currentEpochIndex;

            // Обновляем UI
            const slider = document.getElementById('time-slider');
            const lbl = document.getElementById('lbl-age');
            if (slider) slider.value = currentEpochIndex;
            if (lbl) lbl.innerText = currentEpochIndex;
            
            // Обновляем логи (только если эпоха сменилась)
            if (currentEpoch !== currentEpochIndex) {
                currentEpoch = currentEpochIndex;
                renderLogsUntil(currentEpoch);
            }

            // РИСУЕМ!
            drawWorldSmooth(totalProgress, epochProgress);

            requestAnimationFrame(step);
        }

        requestAnimationFrame(step);
    });
}