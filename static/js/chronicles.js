import { api } from './api.js';

// --- КОНФИГУРАЦИЯ ЦВЕТОВ ---
const TYPE_COLORS = {
    'Biome': '#a8dadc',
    'Location': '#457b9d',
    'Faction': '#e63946',
    'Character': '#f4a261',
    'Resource': '#2a9d8f',
    'Event': '#1d3557',
    'Conflict': '#641414ff',
    'Item': '#ffd700',
    'Ritual': '#9b5de5',
    'Belief': '#00bbf9',
    'Boss': '#614327ff',
    'default': '#999999'
};

// --- СОСТОЯНИЕ ---
let cy = null;
let fullData = { nodes: [], edges: [] };
let currentEpoch = 0;
let maxEpoch = 0;
let selectedNodeId = null;
let hiddenTypes = new Set(); 

// --- 1. ИНИЦИАЛИЗАЦИЯ ---
export function initChronicles() {
    if (cy) return; 
    
    console.log("Chronicles module init...");
    
    const container = document.getElementById('cy');
    if (!container) return;

    initCy(container);
    renderLegend(container.parentElement); // Рисуем легенду и контролы
    addShuffleButton(container.parentElement);

    const slider = document.getElementById('chrono-slider');
    if (slider) {
        slider.addEventListener('input', (e) => {
            currentEpoch = parseInt(e.target.value);
            document.getElementById('chrono-age-display').textContent = currentEpoch;
            renderEpoch(currentEpoch);
        });
    }

    const btnNarrate = document.getElementById('btn-narrate-history');
    if (btnNarrate) btnNarrate.addEventListener('click', generateStory);
}

// --- 2. ЗАГРУЗКА ДАННЫХ (ОБНОВЛЕНО) ---
export async function loadWorldData() {
    console.log("Loading graph data...");
    // TODO: добавить include в запрос и в GUI!
    // Пытаемся найти инпут с тегами (если он уже отрисован)
    const tagsInput = document.getElementById('server-filter-tags');
    let excludeParams = '';
    
    if (tagsInput) {
        const tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t);
        if (tags.length > 0) {
            const params = new URLSearchParams();
            tags.forEach(t => params.append('exclude_tags', t));
            excludeParams = '?' + params.toString();
        }
    } else {
        // Дефолт при первой загрузке
        excludeParams = '?exclude_tags=dead&exclude_tags=inactive'; 
    }

    try {
        // Используем новый эндпоинт, если он есть, иначе старый (фоллбэк)
        let rawData;
        try {
            rawData = await api.get(`/api/simulation/world/graph${excludeParams}`);
        } catch (e) {
            console.warn("New endpoint failed, falling back to legacy", e);
            rawData = await api.get('/api/simulation/latest_graph');
        }

        // --- УНИВЕРСАЛЬНОЕ ИЗВЛЕЧЕНИЕ ДАННЫХ ---
        // Ищем entities либо в корне, либо внутри graph, либо внутри data
        const entitiesDict = rawData.entities || (rawData.graph ? rawData.graph.entities : null);
        
        console.log("API RAW RESPONSE:", rawData);

        if (!entitiesDict || Object.keys(entitiesDict).length === 0) {
            console.warn("Graph data is empty or structure mismatch!", rawData);
            // Если данные пустые, слайдер останется 100 (дефолт HTML),
            // поэтому вручную сбросим его, чтобы не смущать
            const slider = document.getElementById('chrono-slider');
            if(slider) { slider.value = 0; document.getElementById('chrono-age-display').textContent = "0 (No Data)"; }
            return;
        }

        // Если нашли, нормализуем структуру для prepareData
        // Мы передаем объект, у которого точно есть поле entities
        const normalizedData = {
            entities: entitiesDict,
            relations: rawData.relations || (rawData.graph ? rawData.graph.relations : [])
        };

        fullData = prepareData(normalizedData);
        
        maxEpoch = 0;
        if (fullData.nodes.length > 0) {
            maxEpoch = Math.max(...fullData.nodes.map(n => n.data.created_at || 0));
        }
        
        const slider = document.getElementById('chrono-slider');
        if (slider) {
            slider.max = maxEpoch;
            slider.value = maxEpoch; 
        }
        currentEpoch = maxEpoch;
        document.getElementById('chrono-age-display').textContent = currentEpoch;

        if (cy) {
            cy.resize();
            updateLegendItems(); // Обновляем чекбоксы типов
            renderEpoch(currentEpoch, true);
        }
        
        // Показываем тост или статус
        console.log(`Loaded ${fullData.nodes.length} nodes.`);

    } catch (e) {
        console.error("Ошибка загрузки графа:", e);
        alert("Не удалось загрузить граф. Проверьте консоль.");
    }
}

// --- ПАРСИНГ ДАННЫХ ---
function prepareData(json) {
    // 1. Сначала собираем узлы
    const nodes = Object.values(json.entities).map(e => ({
        group: 'nodes',
        data: { 
            id: e.id, label: e.name || e.id, type: e.type, 
            created_at: e.created_at || 0, parent_id: e.parent_id, raw: e 
        }
    }));

    // Создаем Set ID для быстрой проверки существования
    const nodeIds = new Set(nodes.map(n => n.data.id));

    const edges = [];

    // 2. Обрабатываем обычные связи (Relations)
    if (json.relations) {
        json.relations.forEach((r, i) => {
            // Проверяем, существуют ли оба конца связи
            if (nodeIds.has(r.from_entity.id) && nodeIds.has(r.to_entity.id)) {
                edges.push({
                    group: 'edges',
                    data: {
                        id: `rel_${i}`, source: r.from_entity.id, target: r.to_entity.id,
                        label: r.relation_type.id,
                        created_at: Math.max(r.from_entity.created_at || 0, r.to_entity.created_at || 0)
                    }
                });
            }
        });
    }

    // 3. Обрабатываем иерархию (Parent -> Child)
    // ИСПРАВЛЕНИЕ: Добавляем связь только если родитель существует в текущем наборе данных
    nodes.forEach(n => {
        if (n.data.parent_id && nodeIds.has(n.data.parent_id)) {
            edges.push({
                group: 'edges',
                data: {
                    id: `hier_${n.data.id}_${n.data.parent_id}`,
                    source: n.data.id,
                    target: n.data.parent_id,
                    type: 'hierarchy', // специальный тип для стиля
                    created_at: n.data.created_at
                }
            });
        }
    });

    return { nodes, edges };
}

// --- VISUALIZATION HELPERS (ОБНОВЛЕНО UI) ---
function renderLegend(parentContainer) {
    if (parentContainer.querySelector('#graph-legend')) return;
    
    const legendDiv = document.createElement('div');
    legendDiv.id = 'graph-legend';
    legendDiv.className = 'card shadow-sm position-absolute top-0 start-0 m-3 p-2';
    legendDiv.style.zIndex = 1000;
    legendDiv.style.width = '240px'; // Чуть шире для инпутов
    legendDiv.style.maxHeight = '75vh';
    legendDiv.style.overflowY = 'auto';
    legendDiv.style.opacity = '0.95';
    legendDiv.style.fontSize = '0.85rem';

    // HTML Легенды с новыми контролами
    legendDiv.innerHTML = `
        <h6 class="border-bottom pb-2 mb-2"><i class="fas fa-filter"></i> Данные</h6>
        
        <div class="mb-3 p-2 bg-light border rounded">
            <label class="form-label small fw-bold mb-1">Исключить теги (Server):</label>
            <input type="text" id="server-filter-tags" class="form-control form-control-sm mb-2" value="dead, inactive, historical">
            <button id="btn-reload-server" class="btn btn-primary btn-sm w-100">
                <i class="fas fa-sync-alt"></i> Обновить граф
            </button>
        </div>

        <h6 class="border-bottom pb-2 mb-2"><i class="fas fa-eye"></i> Видимость типов</h6>
        <div id="legend-items"></div>
    `;
    
    parentContainer.style.position = 'relative';
    parentContainer.appendChild(legendDiv);

    // Вешаем обработчик на кнопку обновления
    document.getElementById('btn-reload-server').onclick = () => loadWorldData();
}

function updateLegendItems() {
    const container = document.getElementById('legend-items');
    if (!container) return;
    const types = new Set(fullData.nodes.map(n => n.data.type));
    container.innerHTML = '';

    types.forEach(type => {
        const color = TYPE_COLORS[type] || TYPE_COLORS['default'];
        const isChecked = !hiddenTypes.has(type);
        const item = document.createElement('div');
        item.className = 'form-check d-flex align-items-center mb-1';
        item.innerHTML = `
            <input class="form-check-input me-2" type="checkbox" value="${type}" id="filter-${type}" ${isChecked ? 'checked' : ''}>
            <label class="form-check-label d-flex align-items-center" for="filter-${type}" style="cursor:pointer; width: 100%;">
                <span style="display:inline-block; width:12px; height:12px; background-color:${color}; border-radius:2px; margin-right:8px;"></span>${type}
            </label>`;
        
        item.querySelector('input').addEventListener('change', (e) => {
            e.target.checked ? hiddenTypes.delete(type) : hiddenTypes.add(type);
            renderEpoch(currentEpoch);
        });
        container.appendChild(item);
    });
}

// --- CYTOSCAPE SETUP ---
function initCy(container) {
    cy = cytoscape({
        container: container,
        elements: [], 
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': ele => TYPE_COLORS[ele.data('type')] || TYPE_COLORS['default'],
                    'label': 'data(label)',
                    'color': '#333', 'font-size': '10px',
                    'width': 20, 'height': 20,
                    'text-valign': 'center', 'text-halign': 'center',
                    'text-outline-color': '#fff', 'text-outline-width': 1
                }
            },
            {
                selector: 'node[type="Biome"]',
                style: { 
                    'width': 70, 'height': 70, 'font-size': '12px', 
                    'opacity': 0.6, 'z-index': -1, 'shape': 'hexagon',
                    'text-valign': 'center'
                }
            },
            {
                selector: 'node[type="Location"]',
                style: { 'shape': 'rectangle', 'width': 30, 'height': 30 }
            },
            {
                selector: 'edge', // Обычные связи
                style: {
                    'width': 1, 'line-color': '#ccc',
                    'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier', 'opacity': 0.5
                }
            },
            {
                selector: 'edge[type="hierarchy"]', // Стиль для родительских связей
                style: {
                    'width': 1, 
                    'line-color': '#bbb', 
                    'line-style': 'dashed',
                    'curve-style': 'straight',
                    'target-arrow-shape': 'none' // Без стрелки для иерархии
                }
            },
            {
                selector: ':selected',
                style: {
                    'border-width': 3, 'border-color': '#222',
                    'background-color': '#fff', 'z-index': 999
                }
            }
        ],
        layout: { name: 'preset' }
    });

    cy.on('tap', 'node', evt => showNodeDetails(evt.target));
}

function renderEpoch(epoch, forceLayout = false) {
    if (!cy) return;
    
    // Фильтр по времени и скрытым типам (клиентский)
    let visibleNodes = fullData.nodes.filter(n => n.data.created_at <= epoch);
    visibleNodes = visibleNodes.filter(n => !hiddenTypes.has(n.data.type));
    
    const visibleNodeIds = new Set(visibleNodes.map(n => n.data.id));
    
    // Фильтр ребер: оба конца должны быть видимы
    const visibleEdges = fullData.edges.filter(e => 
        visibleNodeIds.has(e.data.source) && visibleNodeIds.has(e.data.target)
    );

    cy.batch(() => {
        // Удаляем лишнее
        cy.nodes().forEach(n => { if (!visibleNodeIds.has(n.id())) cy.remove(n); });
        
        // Добавляем новое
        const nodesToAdd = visibleNodes.filter(n => cy.getElementById(n.data.id).empty());
        const edgesToAdd = visibleEdges.filter(e => cy.getElementById(e.data.id).empty());

        if (nodesToAdd.length > 0) {
            nodesToAdd.forEach(n => {
                // Если есть родитель и он уже на графе -> ставим рядом
                if (n.data.parent_id) {
                    const parent = cy.getElementById(n.data.parent_id);
                    if (parent.nonempty()) {
                        const pp = parent.position();
                        n.position = { 
                            x: pp.x + (Math.random()-0.5)*60, 
                            y: pp.y + (Math.random()-0.5)*60 
                        };
                    } else {
                        n.position = { x: Math.random()*800, y: Math.random()*600 };
                    }
                } else {
                     n.position = { x: Math.random()*800, y: Math.random()*600 };
                }
            });
            cy.add(nodesToAdd);
        }
        
        // Добавляем ребра (только если их нет)
        if (edgesToAdd.length > 0) {
            cy.add(edgesToAdd);
        }
    });

    if (forceLayout || (visibleNodes.length > 0 && visibleNodes.length > cy.nodes().length)) {
        cy.layout({ 
            name: 'cose', 
            animate: true, 
            animationDuration: 500, 
            randomize: false, 
            nodeRepulsion: 400000,
            componentSpacing: 60
        }).run();
    }
}

function addShuffleButton(parentContainer) {
    if (parentContainer.querySelector('#btn-shuffle-graph')) return;
    const btn = document.createElement('button');
    btn.id = 'btn-shuffle-graph';
    btn.className = 'btn btn-light btn-sm position-absolute top-0 end-0 m-3 shadow';
    btn.style.zIndex = 1000;
    btn.innerHTML = '<i class="fas fa-random"></i> Перемешать';
    btn.onclick = () => { if (cy) cy.layout({ name: 'cose', animate: true, randomize: true }).run(); };
    parentContainer.appendChild(btn);
}

// --- INFO PANEL & LLM ---
function showNodeDetails(node) {
    selectedNodeId = node.id();
    const data = node.data('raw');
    const container = document.getElementById('info-details');
    const typeColor = TYPE_COLORS[data.type] || '#666';

    let html = `
        <h5>${data.name}</h5>
        <span class="badge mb-2" style="background-color: ${typeColor}">${data.type}</span>
        <div class="small text-muted mb-3">ID: ${data.id}</div>
        
        <button id="btn-describe-entity" class="btn btn-outline-primary btn-sm w-100 mb-3">
            <i class="fas fa-magic"></i> Описать с AI
        </button>
        <div id="ai-description-output" class="mb-3 small p-2 bg-light border rounded" style="display:none"></div>
        <hr><h6>Свойства:</h6>
        <div class="table-responsive"><table class="table table-sm table-borderless small"><tbody>
    `;
    
    for (const [key, val] of Object.entries(data)) {
        if(['id', 'name', 'type', 'created_at', 'parent_id', 'definition_id', 'tags'].includes(key)) continue;
        let displayVal = typeof val === 'object' ? JSON.stringify(val) : val;
        html += `<tr><td class="text-muted">${key}:</td><td>${displayVal}</td></tr>`;
    }
    
    if (data.tags) {
        html += `<tr><td class="text-muted">Tags:</td><td>${Array.from(data.tags).join(', ')}</td></tr>`;
    }

    html += `</tbody></table></div>`;
    container.innerHTML = html;
    document.getElementById('btn-describe-entity').onclick = () => getLlmDescription(selectedNodeId);
}

async function getLlmDescription(entityId) {
    const outDiv = document.getElementById('ai-description-output');
    const btn = document.getElementById('btn-describe-entity');
    
    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Думаю...';
        outDiv.style.display = 'block';
        outDiv.textContent = 'Генерация описания...';
        
        const response = await fetch('/api/simulation/describe_entity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_id: entityId })
        });

        if (!response.ok) throw new Error(`Server error: ${response.status}`);

        const data = await response.json();
        outDiv.innerHTML = window.marked ? marked.parse(data.text) : data.text;
        
    } catch (e) {
        outDiv.innerHTML = `<span class="text-danger">Ошибка: ${e.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> Описать снова';
    }
}

async function generateStory() {
    const output = document.getElementById('story-output');
    const btn = document.getElementById('btn-narrate-history');
    const settingInput = document.getElementById('story-setting');
    const setting = settingInput ? settingInput.value : "Dark Fantasy";
    
    if (!fullData || !fullData.nodes || fullData.nodes.length === 0) {
        output.innerHTML = "Данные мира еще не загружены.";
        return;
    }

    const eventNodes = fullData.nodes.filter(n => {
        const t = n.data.type;
        const isCorrectType = (t === 'Event' || t === 'Conflict');
        const isCorrectEpoch = (currentEpoch === 0) ? true : (n.data.created_at === currentEpoch);
        return isCorrectType && isCorrectEpoch;
    });

    if (eventNodes.length === 0) {
        output.innerHTML = `Нет событий для описания в эпоху ${currentEpoch}.`;
        return;
    }

    const eventsToSend = eventNodes.map(n => n.data.raw);

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Пишу...';
        output.innerHTML = '<i>Летописец скрипит пером...</i>';

        const res = await fetch('/api/simulation/narrate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                events: eventsToSend,
                setting: setting,
                examples: ["Dark Souls", "Elden Ring"] 
            })
        });

        if (!res.ok) throw new Error("Ошибка генерации");

        const data = await res.json();
        const text = data.text || data.story || "История пуста.";
        output.innerHTML = window.marked ? marked.parse(text) : text;

    } catch (e) {
        console.error(e);
        output.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-feather-alt"></i> Описать эпоху';
    }
}