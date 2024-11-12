// app.js

let allTranslations = [];
let filteredTranslations = [];
let currentContext = '';
let searchResults = [];
let searchIndex = -1;
let currentTab = 'pcb'; // 默认标签
let authToken = localStorage.getItem('authToken');

// 处理标签点击事件
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        currentTab = button.getAttribute('data-tab');
        // 更新按钮的active状态
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        // 从服务器获取对应标签的数据
        fetchTranslationsFromServer();
    });
});

// 获取元素引用
const importButton = document.getElementById('importButton');
importButton.style.display = 'none';
const exportButton = document.getElementById('exportButton');
const prevButton = document.getElementById('prevButton');
prevButton.style.display = 'none';
const nextButton = document.getElementById('nextButton');
nextButton.style.display = 'none';
const statusFilter = document.getElementById('statusFilter');
const searchBox = document.getElementById('searchBox');
searchBox.style.display = 'none';
const gitSyncButton = document.getElementById('gitSyncButton');

// 添加事件监听器
// importButton.addEventListener('click', importFromTS);
exportButton.addEventListener('click', exportToTS);
prevButton.addEventListener('click', () => search('prev'));
nextButton.addEventListener('click', () => search('next'));
statusFilter.addEventListener('change', applyFilter);
searchBox.addEventListener('input', updateSearchResults);
gitSyncButton.addEventListener('click', syncFromGit);

// 获取翻译数据
async function fetchTranslationsFromServer() {
    const response = await fetch(`/get_translations?tab=${currentTab}`);
    if (response.ok) {
        allTranslations = await response.json();

        // 如果是message类型，确保message_id字段存在
        if (currentTab === 'message') {
            allTranslations = allTranslations.map(item => ({
                ...item,
                message_id: item.message_id || ''
            }));
        }

        displayContexts(allTranslations);
        currentContext = '';
        document.getElementById('translations').innerHTML = '';
    } else {
        alert('Error loading translations from server');
    }
}

// 显示上下文列表
function displayContexts(translations) {
    const contextNav = document.getElementById('context-nav');
    const contexts = [...new Set(translations.map(item => item.context))];
    contextNav.innerHTML = '';

    contexts.forEach(context => {
        const contextItems = translations.filter(item => item.context === context);
        const totalItems = contextItems.length;
        const translatedItems = contextItems.filter(item => item.status === 'translated').length;
        const unfinishedItems = contextItems.filter(item => item.status === 'unfinished').length;
        const obsoleteItems = contextItems.filter(item => item.status === 'obsolete').length;

        let statusClass = 'unfinished';
        if (unfinishedItems === 0 && obsoleteItems === 0) {
            statusClass = 'translated';
        } else if (translatedItems === 0 && unfinishedItems > 0) {
            statusClass = 'unfinished';
        } else if (obsoleteItems > 0) {
            statusClass = 'obsolete';
        }

        const contextDiv = document.createElement('div');
        contextDiv.className = `context-item ${statusClass}`;
        contextDiv.innerHTML = `
            <span>${context}</span>
            <span>${translatedItems}/${totalItems}</span>
        `;
        contextDiv.setAttribute('data-tooltip', `Unfinished: ${unfinishedItems}\nTranslated: ${translatedItems}\nObsolete: ${obsoleteItems}`);
        contextDiv.onclick = () => {
            currentContext = context;
            displayTranslations(context);
            document.querySelectorAll('.context-item').forEach(item => item.classList.remove('selected'));
            contextDiv.classList.add('selected');
        };
        contextNav.appendChild(contextDiv);
    });
}

// 显示翻译项
function displayTranslations(selectedContext) {
    const container = document.getElementById('translations');
    container.innerHTML = '';
    filteredTranslations = allTranslations.filter(item => item.context === selectedContext);

    filteredTranslations.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = `translation-item item-${item.id} ${item.status}`;
        div.innerHTML = `
            <div>
                <p><strong>Source:</strong></p>
                <div class="source-box">${item.source}</div>
                <p><strong>Translation:</strong></p>
                <textarea id="translation_${item.id}" 
                          class="translation-textarea"
                          onchange="onTranslationChange(${item.id})"
                          onkeydown="handleKeyPress(event, ${item.id})">${item.translation}</textarea>
                <p><strong>Status:</strong> 
                    <select id="status_${item.id}"  class="status-select" onchange="updateTranslation(${item.id})">
                        <option value="unfinished" ${item.status === 'unfinished' ? 'selected' : ''}>Unfinished</option>
                        <option value="translated" ${item.status === 'translated' ? 'selected' : ''}>Translated</option>
                        <option value="obsolete" ${item.status === 'obsolete' ? 'selected' : ''}>Obsolete</option>
                    </select>
                </p>
                <p><strong>Comment:</strong> ${item.comment}</p>
            </div>
        `;
        container.appendChild(div);
    });
    applyFilter();
}
function handleKeyPress(event, id) {
    if (event.ctrlKey && event.key === 'Enter') {
        event.preventDefault(); // 防止默认的回车换行行为
        // 获取输入框的值
        const translationInput = document.getElementById(`translation_${id}`);
        const newTranslation = translationInput.value;

        // 自动将状态设置为 'translated'
        const statusSelect = document.getElementById(`status_${id}`);
        statusSelect.value = 'translated';

        // 更新本地数据
        const translation = allTranslations.find(item => item.id === id);
        if (translation) {
            translation.translation = newTranslation;
            translation.status = 'translated';
        }

        // 更新服务器数据
        updateTranslation(id);

        // 查找下一个未翻译的item
        const nextUnfinishedItem = filteredTranslations.find(item => item.id > id && item.status === 'unfinished');

        if (nextUnfinishedItem) {
            // 如果找到下一个未翻译的item，聚焦到它的输入框
            const nextInput = document.getElementById(`translation_${nextUnfinishedItem.id}`);
            if (nextInput) {
                nextInput.focus();
            }
        } else {
            // 如果没有找到未翻译的item，让当前输入框失去焦点
            translationInput.blur();
        }
    }
}

function onTranslationChange(id) {
    // 获取输入框的值
    const translationInput = document.getElementById(`translation_${id}`);
    const newTranslation = translationInput.value;

    // 获取当前状态
    const statusSelect = document.getElementById(`status_${id}`);
    const newStatus = statusSelect.value;

    // 更新本地数据
    const translation = allTranslations.find(item => item.id === id);
    if (translation) {
        translation.translation = newTranslation;
        translation.status = "translated";
    }

    // 更新服务器数据
    updateTranslation(id);
}


// 更新翻译
async function updateTranslation(id) {
    const translationInput = document.getElementById(`translation_${id}`);
    const statusSelect = document.getElementById(`status_${id}`);
    const newTranslation = translationInput.value;
    const newStatus = statusSelect.value;

    // 更新本地数据
    const translation = allTranslations.find(item => item.id === id);
    if (translation) {
        translation.translation = newTranslation;
        translation.status = newStatus;
    }

    // 准备请求数据
    const requestData = {
        id,
        translation: newTranslation,
        status: newStatus,
        tab: currentTab
    };

    // 如果是message类型，添加message_id
    if (currentTab === 'message' && translation) {
        requestData.message_id = translation.message_id;
    }

    // 更新服务器数据
    const response = await fetch('/update_translation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
    });

    if (!response.ok) {
        alert('Error updating translation');
    } else {
        if (!response.ok) {
            alert('Error updating translation');
        } else {
            updateContextStatus();
            // 更新翻译项的样式
            const translationItem = document.querySelector(`.item-${id}`);
            if (translationItem) {
                // 移除所有可能的状态类
                translationItem.classList.remove('unfinished', 'translated', 'obsolete');
                // 添加新的状态类
                translationItem.classList.add(newStatus);
            }
        }
    }
}

// 应用筛选器
function applyFilter() {
    const filterValue = statusFilter.value.toLowerCase();
    const container = document.getElementById('translations');

    container.childNodes.forEach(child => {
        if (child.nodeType !== Node.ELEMENT_NODE) return;
        if (filterValue === 'all' || child.classList.contains(filterValue)) {
            child.style.display = '';
        } else {
            child.style.display = 'none';
        }
    });
}

// 更新搜索结果
function updateSearchResults() {
    const searchQuery = searchBox.value.toLowerCase();
    searchResults = [];

    if (searchQuery) {
        allTranslations.forEach((item, index) => {
            if (item.context.toLowerCase().includes(searchQuery)) {
                searchResults.push({ type: 'context', value: item.context });
            } else if (item.source.toLowerCase().includes(searchQuery) || item.translation.toLowerCase().includes(searchQuery)) {
                searchResults.push({ type: 'message', context: item.context, index });
            }
        });
    }

    searchIndex = -1;
}

// 搜索功能
function search(direction) {
    if (searchResults.length === 0) return;

    if (direction === 'next') {
        searchIndex = (searchIndex + 1) % searchResults.length;
    } else if (direction === 'prev') {
        searchIndex = (searchIndex - 1 + searchResults.length) % searchResults.length;
    }

    const result = searchResults[searchIndex];
    if (result.type === 'context') {
        document.querySelectorAll('.context-item').forEach(div => {
            if (div.textContent.includes(result.value)) {
                div.scrollIntoView({ behavior: 'smooth' });
                div.click();
            }
        });
    } else if (result.type === 'message') {
        document.querySelectorAll('.context-item').forEach(div => {
            if (div.textContent.includes(result.context)) {
                div.click();
            }
        });
        setTimeout(() => {
            const container = document.getElementById('translations');
            container.childNodes.forEach((child, childIndex) => {
                if (child.nodeType !== Node.ELEMENT_NODE) return;
                if (childIndex === result.index) {
                    child.scrollIntoView({ behavior: 'smooth' });
                    child.classList.add('highlighted');
                    setTimeout(() => {
                        child.classList.remove('highlighted');
                    }, 3000);
                }
            });
        }, 300);
    }
}

// 更新上下文状态
function updateContextStatus() {
    const contextNav = document.getElementById('context-nav');
    const contextDiv = Array.from(contextNav.children).find(div => div.textContent.includes(currentContext));
    const contextItems = allTranslations.filter(item => item.context === currentContext);
    const totalItems = contextItems.length;
    const translatedItems = contextItems.filter(item => item.status === 'translated').length;
    const unfinishedItems = contextItems.filter(item => item.status === 'unfinished').length;
    const obsoleteItems = contextItems.filter(item => item.status === 'obsolete').length;

    let statusClass = 'unfinished';
    if (unfinishedItems === 0 && obsoleteItems === 0) {
        statusClass = 'translated';
    } else if (translatedItems === 0 && unfinishedItems > 0) {
        statusClass = 'unfinished';
    } else if (obsoleteItems > 0) {
        statusClass = 'obsolete';
    }

    if (contextDiv) {
        contextDiv.className = `context-item ${statusClass}`;
        contextDiv.innerHTML = `
            <span>${currentContext}</span>
            <span>${translatedItems}/${totalItems}</span>
        `;
        contextDiv.setAttribute('data-tooltip', `Unfinished: ${unfinishedItems}\nTranslated: ${translatedItems}\nObsolete: ${obsoleteItems}`);
    }
}

// 导入TS文件
async function importFromTS() {
    const input = document.getElementById('fileInput');
    const file = input.files[0];

    if (!file) {
        alert("Please select a file to upload.");
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('tab', currentTab); // 添加当前标签

    const response = await fetch('/import_from_ts', {
        method: 'POST',
        body: formData
    });

    if (response.ok) {
        alert('File imported successfully');
        fetchTranslationsFromServer();
    } else {
        alert('Error importing file');
    }
}

// 导出到TS文件
async function exportToTS() {
    const fileName = document.getElementById('exportFileName').value;
    if (!fileName) {
        alert("Please enter a file name for export.");
        return;
    }

    const response = await fetch('/export_to_ts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ file_name: fileName, tab: currentTab })
    });

    if (response.ok) {
        alert('File exported successfully');
    } else {
        alert('Error exporting file');
    }
}

// 同步函数
async function syncFromGit() {
    gitSyncButton.disabled = true;
    gitSyncButton.textContent = 'Syncing...';

    try {
        const response = await fetch('/sync_from_git', {
            method: 'POST'
        });

        if (response.ok) {
            alert('Git sync completed successfully');
            // 重新加载当前标签的翻译数据
            await fetchTranslationsFromServer();
        } else {
            const errorText = await response.text();
            alert(`Error syncing from git: ${errorText}`);
        }
    } catch (error) {
        alert(`Error syncing from git: ${error.message}`);
    } finally {
        gitSyncButton.disabled = false;
        gitSyncButton.textContent = 'Sync from Git';
    }
}

// 页面加载时获取默认标签的数据
document.addEventListener('DOMContentLoaded', () => {
    fetchTranslationsFromServer();
});

