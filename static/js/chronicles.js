import { api } from './api.js';

// --- КОНФИГУРАЦИЯ ЦВЕТОВ ---
const TYPE_COLORS = {
    'Biome': '#a8dadc',
    'Location': '#457b9d',
    'Faction': '#e63946',
    'Character': '#f4a261',
    'Resource': '#2a9d8f',
    'Event': '#1d3557',
    'Conflict': '#d62828',
    'Item': '#ffd700',
    'Ritual': '#9b5de5',
    'Belief': '#00bbf9',
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
    renderLegend(container.parentElement);
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

// --- 2. ЗАГРУЗКА ДАННЫХ ---
export async function loadWorldData() {
    console.log("Loading graph data...");
    
    try {
        const rawData = await api.get('/api/simulation/latest_graph'); 
        
        if (!rawData || !rawData.entities) {
            console.warn("Graph data is empty");
            return;
        }

        fullData = prepareData(rawData);
        
        maxEpoch = 0;
        if (fullData.nodes.length > 0) {
            maxEpoch = Math.max(...fullData.nodes.map(n => n.data.created_at || 0));
        }
        
        const slider = document.getElementById('chrono-slider');
        if (slider) {
            slider.max = maxEpoch;
            slider.value = maxEpoch; // Ставим на последнюю эпоху
        }
        currentEpoch = maxEpoch;
        document.getElementById('chrono-age-display').textContent = currentEpoch;

        if (cy) {
            cy.resize();
            updateLegendItems();
            renderEpoch(currentEpoch, true);
        }

    } catch (e) {
        console.error("Ошибка загрузки графа:", e);
    }
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
                    'width': 60, 'height': 60, 'font-size': '12px', 
                    'opacity': 0.6, 'z-index': -1, 'shape': 'hexagon'
                }
            },
            {
                selector: 'node[type="Location"]',
                style: { 'shape': 'rectangle', 'width': 30, 'height': 30 }
            },
            {
                selector: 'node[type="Faction"]',
                style: { 'shape': 'ellipse', 'border-width': 2, 'border-color': '#333' }
            },
            {
                selector: 'edge',
                style: {
                    'width': 1, 'line-color': '#ccc',
                    'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier', 'opacity': 0.5
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

// --- VISUALIZATION HELPERS ---
function renderLegend(parentContainer) {
    if (parentContainer.querySelector('#graph-legend')) return;
    const legendDiv = document.createElement('div');
    legendDiv.id = 'graph-legend';
    legendDiv.className = 'card shadow-sm position-absolute top-0 start-0 m-3 p-2';
    legendDiv.style.zIndex = 1000;
    legendDiv.style.maxWidth = '200px';
    legendDiv.style.maxHeight = '60vh';
    legendDiv.style.overflowY = 'auto';
    legendDiv.style.opacity = '0.95';
    legendDiv.style.fontSize = '0.85rem';

    legendDiv.innerHTML = `<h6 class="border-bottom pb-2 mb-2"><i class="fas fa-filter"></i> Фильтры</h6><div id="legend-items"></div>`;
    parentContainer.style.position = 'relative';
    parentContainer.appendChild(legendDiv);
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

function prepareData(json) {
    const nodes = Object.values(json.entities).map(e => ({
        group: 'nodes',
        data: { 
            id: e.id, label: e.name || e.id, type: e.type, 
            created_at: e.created_at || 0, parent_id: e.parent_id, raw: e 
        }
    }));
    const edges = (json.relations || []).map((r, i) => ({
        group: 'edges',
        data: {
            id: `rel_${i}`, source: r.from_entity.id, target: r.to_entity.id,
            label: r.relation_type.id,
            created_at: Math.max(r.from_entity.created_at || 0, r.to_entity.created_at || 0)
        }
    }));
    return { nodes, edges };
}

function renderEpoch(epoch, forceLayout = false) {
    if (!cy) return;
    let visibleNodes = fullData.nodes.filter(n => n.data.created_at <= epoch);
    visibleNodes = visibleNodes.filter(n => !hiddenTypes.has(n.data.type));
    const visibleNodeIds = new Set(visibleNodes.map(n => n.data.id));
    const visibleEdges = fullData.edges.filter(e => visibleNodeIds.has(e.data.source) && visibleNodeIds.has(e.data.target));

    cy.batch(() => {
        cy.nodes().forEach(n => { if (!visibleNodeIds.has(n.id())) cy.remove(n); });
        const nodesToAdd = visibleNodes.filter(n => cy.getElementById(n.data.id).empty());
        const edgesToAdd = visibleEdges.filter(e => cy.getElementById(e.data.id).empty());

        if (nodesToAdd.length > 0) {
            nodesToAdd.forEach(n => {
                if (n.data.parent_id) {
                    const parent = cy.getElementById(n.data.parent_id);
                    if (parent.nonempty()) {
                        const pp = parent.position();
                        n.position = { x: pp.x + (Math.random()-0.5)*50, y: pp.y + (Math.random()-0.5)*50 };
                    } else {
                        n.position = { x: Math.random()*500, y: Math.random()*500 };
                    }
                }
            });
            cy.add(nodesToAdd);
        }
        if (edgesToAdd.length > 0) cy.add(edgesToAdd);
    });

    if (forceLayout || (visibleNodes.length > 0 && visibleNodes.length > cy.nodes().length)) {
        cy.layout({ name: 'cose', animate: true, animationDuration: 500, randomize: false, nodeRepulsion: 400000 }).run();
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
        if(['id', 'name', 'type', 'created_at', 'parent_id', 'definition_id'].includes(key)) continue;
        let displayVal = typeof val === 'object' ? JSON.stringify(val) : val;
        html += `<tr><td class="text-muted">${key}:</td><td>${displayVal}</td></tr>`;
    }
    
    html += `</tbody></table></div>`;
    container.innerHTML = html;
    document.getElementById('btn-describe-entity').onclick = () => getLlmDescription(selectedNodeId);
}

// 1. ИСПРАВЛЕНИЕ: Используем правильный Endpoint и POST
async function getLlmDescription(entityId) {
    const outDiv = document.getElementById('ai-description-output');
    const btn = document.getElementById('btn-describe-entity');
    
    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Думаю...';
        outDiv.style.display = 'block';
        outDiv.textContent = 'Генерация описания...';
        
        // Исправленный запрос
        const response = await fetch('/api/simulation/describe_entity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_id: entityId })
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();
        // Рендерим Markdown, если подключен, иначе текст
        outDiv.innerHTML = window.marked ? marked.parse(data.text) : data.text;
        
    } catch (e) {
        outDiv.innerHTML = `<span class="text-danger">Ошибка: ${e.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> Описать снова';
    }
}

// 2. ИСПРАВЛЕНИЕ: Собираем events перед отправкой
async function generateStory() {
    const output = document.getElementById('story-output');
    const btn = document.getElementById('btn-narrate-history');
    const settingInput = document.getElementById('story-setting');
    const setting = settingInput ? settingInput.value : "Dark Fantasy";
    
    // Проверка, есть ли данные
    if (!fullData || !fullData.nodes || fullData.nodes.length === 0) {
        output.innerHTML = "Данные мира еще не загружены.";
        return;
    }

    // --- ИСПРАВЛЕНИЕ: Собираем события из графа ---
    // Фильтруем узлы, которые являются Событиями или Конфликтами
    // И которые произошли в текущую эпоху (currentEpoch). 
    // Если хотите описывать ВСЁ с начала времен, уберите проверку created_at.
    const eventNodes = fullData.nodes.filter(n => {
        const t = n.data.type;
        // Если currentEpoch > 0, берем события этой эпохи. Если 0 - берем всё (или ничего, зависит от логики)
        const isCorrectType = (t === 'Event' || t === 'Conflict');
        const isCorrectEpoch = (currentEpoch === 0) ? true : (n.data.created_at === currentEpoch);
        
        return isCorrectType && isCorrectEpoch;
    });

    if (eventNodes.length === 0) {
        output.innerHTML = `Нет событий для описания в эпоху ${currentEpoch}. Попробуйте подвигать слайдер времени или запустить симуляцию снова.`;
        return;
    }

    // Извлекаем "сырые" данные (JSON), которые хранятся в data.raw
    const eventsToSend = eventNodes.map(n => n.data.raw);

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Пишу...';
        output.innerHTML = '<i>Летописец скрипит пером...</i>';

        const res = await fetch('/api/simulation/narrate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                events: eventsToSend,      // <-- ПЕРЕДАЕМ СОБРАННЫЙ МАССИВ
                setting: setting,
                examples: ["Dark Souls", "Elden Ring"] 
            })
        });

        if (!res.ok) {
            const err = await res.json();
            console.error("Narrate Error:", err);
            throw new Error(err.detail || "Ошибка генерации");
        }

        const data = await res.json();
        // Сервер возвращает {"text": "..."}
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