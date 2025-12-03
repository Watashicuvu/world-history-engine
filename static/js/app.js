import { initWorkbench } from './workbench.js';
// Используем динамический импорт внутри обработчиков, чтобы не грузить лишнее сразу,
// либо импортируем статически, но функции вызываем лениво.
// Оставим статический импорт для простоты, но изменим логику вызова.
import { initSimulation, loadSimulationData } from './simulation.js';
import { initChronicles, loadWorldData } from './chronicles.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing World Architect...");

    // 1. Инициализируем ТОЛЬКО активную вкладку (Workbench)
    initWorkbench();

    // Флаги состояния, чтобы не вешать обработчики дважды
    const state = {
        simulationInited: false,
        chroniclesInited: false
    };

    // 2. Обработка переключения вкладок
    const tabEls = document.querySelectorAll('button[data-bs-toggle="tab"]');
    
    tabEls.forEach(tabEl => {
        tabEl.addEventListener('shown.bs.tab', event => {
            const targetId = event.target.getAttribute('data-bs-target');

            if (targetId === '#simulation') {
                // Инициализация (вешаем обработчики кнопок) только 1 раз
                if (!state.simulationInited) {
                    initSimulation(); 
                    state.simulationInited = true;
                }
                // Загрузка данных - каждый раз (или можно тоже закрыть флагом)
                loadSimulationData();
            }
            
            if (targetId === '#chronicles') {
                // Инициализация Cytoscape только 1 раз
                if (!state.chroniclesInited) {
                    initChronicles();
                    state.chroniclesInited = true;
                }
                // Загрузка графа
                loadWorldData();
            }
        });
    });
});