import { api } from './api.js';

let editor = null;
let currentConfigType = null;

export function initWorkbench() {
    loadConfigList();
    
    // Save button
    document.getElementById('btn-save-template').addEventListener('click', saveCurrentConfig);
    
    // AI button
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
    document.getElementById('editor-title').textContent = `Editing: ${type}`;
    document.getElementById('btn-save-template').disabled = true;
    
    const holder = document.getElementById('json-editor-holder');
    holder.innerHTML = '<div class="text-center mt-5"><div class="spinner-border"></div></div>';

    try {
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
            collapsed: true // Keeps original templates closed by default
        });

        editor.on('ready', () => {
            document.getElementById('btn-save-template').disabled = false;
        });

        // Naming advice translated
        if (type === 'naming_biomes') {
            const holder = document.getElementById('json-editor-holder');
            
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-info mt-3';
            alertDiv.innerHTML = `
                <i class="fas fa-info-circle"></i> <strong>Grammar Tip:</strong> 
                To ensure correct generation, use words of the 
                <strong>same gender (preferably masculine if relevant)</strong>.
                <br>
                <em>Example:</em> adj=["Dark", "Old"], noun=["Forest", "House"].
            `;
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
        alert('Please fix validation errors!');
        return;
    }

    const btn = document.getElementById('btn-save-template');
    const originalText = btn.innerHTML;
    
    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        
        const data = editor.getValue();
        await api.post(`/api/configs/${currentConfigType}/data`, data);
        
        btn.classList.replace('btn-success', 'btn-outline-success');
        btn.innerHTML = '<i class="fas fa-check"></i> Saved';
        setTimeout(() => {
            btn.classList.replace('btn-outline-success', 'btn-success');
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 2000);
        
    } catch (e) {
        alert('Save error: ' + e.message);
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// --- AI GENERATION ---
async function generateWithAI() {
    if (!editor || !currentConfigType) {
        alert("Please select a template type on the left first.");
        return;
    }

    const promptInput = document.getElementById('ai-prompt');
    const prompt = promptInput.value.trim();
    if (!prompt) {
        alert("Please enter a description.");
        return;
    }

    const btn = document.getElementById('btn-ai-generate');
    const originalText = btn.innerHTML;

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Magic...';

        const newTemplate = await api.post(`/api/llm/suggest/${currentConfigType}`, { prompt });
        
        const currentData = editor.getValue();
        
        if (Array.isArray(currentData)) {
            currentData.push(newTemplate);
            editor.setValue(currentData);
            
            // UX Improvement: Expand the newly added item
            // Get the root editor
            const root = editor.getEditor('root');
            if (root && root.rows) {
                // The last row is the new one
                const lastRow = root.rows[currentData.length - 1];
                if (lastRow) {
                    lastRow.expand();
                    // Scroll into view
                    lastRow.container.scrollIntoView({ behavior: 'smooth' });
                }
            }
            
            alert("✨ Template added to the end of the list!");
        } else {
            console.error("Data structure is not an array", currentData);
            alert("Data structure error");
        }
        
    } catch (e) {
        alert(`Generation error: ${e.message}`);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}