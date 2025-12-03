import { api } from './api.js';

let editor = null;
let currentConfigType = null;

export function initWorkbench() {
    loadConfigList();
    
    // Кнопка сохранения
    document.getElementById('btn-save-template').addEventListener('click', saveCurrentConfig);
    
    // Кнопка AI
    document.getElementById('btn-ai-generate').addEventListener('click', generateWithAI);
}

async function loadConfigList() {
    const list = document.getElementById('config-list');
    try {
        const configs = await api.get('/api/configs');
        
        list.innerHTML = '';
        configs.forEach(type => {
            const btn = document.createElement('button');
            btn.className = 'list-group-item list-group-item-action';
            btn.textContent = type.charAt(0).toUpperCase() + type.slice(1); // Capitalize
            btn.onclick = () => loadEditor(type, btn);
            list.appendChild(btn);
        });
    } catch (e) {
        list.innerHTML = `<div class="text-danger p-2">Error: ${e.message}</div>`;
    }
}

async function loadEditor(type, btnElement) {
    currentConfigType = type;
    
    // UI Updates
    document.querySelectorAll('#config-list button').forEach(b => b.classList.remove('active'));
    btnElement.classList.add('active');
    document.getElementById('editor-title').textContent = `Редактирование: ${type}`;
    document.getElementById('btn-save-template').disabled = true;
    
    const holder = document.getElementById('json-editor-holder');
    holder.innerHTML = '<div class="text-center mt-5"><div class="spinner-border"></div></div>';

    try {
        // Параллельная загрузка схемы и данных
        const [schema, data] = await Promise.all([
            api.get(`/api/configs/${type}/schema`),
            api.get(`/api/configs/${type}/data`)
        ]);

        holder.innerHTML = '';
        
        if (editor) editor.destroy();

        editor = new JSONEditor(holder, {
            schema: schema,
            startval: data,
            theme: 'bootstrap5',
            iconlib: 'fontawesome5',
            disable_edit_json: true,
            disable_properties: true,
            collapsed: true
        });

        editor.on('ready', () => {
            document.getElementById('btn-save-template').disabled = false;
        });

        // После успешной загрузки редактора добавляем warning, если это нейминг
        if (type === 'naming_biomes') {
            const holder = document.getElementById('json-editor-holder');
            
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-info mt-3';
            alertDiv.innerHTML = `
                <i class="fas fa-info-circle"></i> <strong>Совет по грамматике:</strong> 
                Чтобы названия генерировались корректно, используйте слова 
                <strong>одного рода (лучше мужского)</strong>.
                <br>
                <em>Пример:</em> adj=["Старый", "Мрачный"], noun=["Дом", "Лес"]. 
                Тогда "Старый Лес" звучит верно. ("Старая Лес" — ошибка).
            `;
            // Вставляем перед редактором
            holder.prepend(alertDiv);
        }

    } catch (e) {
        holder.innerHTML = `<div class="alert alert-danger">${e.message}</div>`;
    }
}

async function saveCurrentConfig() {
    if (!editor || !currentConfigType) return;
    
    const errors = editor.validate();
    if (errors.length) {
        alert('Исправьте ошибки валидации!');
        return;
    }

    const btn = document.getElementById('btn-save-template');
    const originalText = btn.innerHTML;
    
    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Сохранение...';
        
        const data = editor.getValue();
        await api.post(`/api/configs/${currentConfigType}/data`, data);
        
        // Визуальное подтверждение
        btn.classList.replace('btn-success', 'btn-outline-success');
        btn.innerHTML = '<i class="fas fa-check"></i> Сохранено';
        setTimeout(() => {
            btn.classList.replace('btn-outline-success', 'btn-success');
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 2000);
        
    } catch (e) {
        alert('Ошибка сохранения: ' + e.message);
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// --- AI GENERATION ---
async function generateWithAI() {
    if (!editor || !currentConfigType) {
        alert("Сначала выберите тип шаблона слева.");
        return;
    }

    const promptInput = document.getElementById('ai-prompt');
    const prompt = promptInput.value.trim();
    if (!prompt) {
        alert("Введите описание.");
        return;
    }

    const btn = document.getElementById('btn-ai-generate');
    const originalText = btn.innerHTML;

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Магия...';

        // 1. Запрос к LLM
        const newTemplate = await api.post(`/api/llm/suggest/${currentConfigType}`, { prompt });
        
        // 2. Добавление в редактор
        // JSONEditor работает с массивами, так что нам нужно добавить элемент в массив
        const currentData = editor.getValue();
        
        // Проверяем, массив ли это (должен быть массивом, т.к. наши конфиги - списки)
        if (Array.isArray(currentData)) {
            currentData.push(newTemplate);
            editor.setValue(currentData);
            
            // Прокрутка вниз к новому элементу (хак для json-editor)
            // editor.getEditor('root').rows[currentData.length - 1].expand();
            alert("✨ Шаблон добавлен в конец списка!");
        } else {
            console.error("Структура данных не массив", currentData);
            alert("Ошибка структуры данных");
        }
        
    } catch (e) {
        alert(`Ошибка генерации: ${e.message}`);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}