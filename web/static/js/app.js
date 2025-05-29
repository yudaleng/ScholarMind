class ScholarMindApp {
    constructor() {
        this.uploadedFiles = [];
        this.config = null;
        this.processingInterval = null;
        this.selectedFile = null;
        this.processStartTime = null;
        this.lastProgressUpdate = null;
        this.progressHistory = [];
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadConfig();
        this.loadTemplates();
        this.initSmoothScroll();
    }

    bindEvents() {
        // 文件上传
        document.getElementById('uploadBtn').addEventListener('click', () => this.uploadFile());
        
        // 文件选择反馈
        document.getElementById('fileInput').addEventListener('change', (e) => this.handleFileSelection(e));
        
        // 数据处理
        document.getElementById('processBtn').addEventListener('click', () => this.processData());
        
        // 配置变更监听
        document.getElementById('journalMetricsEnabled').addEventListener('change', (e) => {
            this.toggleJournalMetricsConfig(e.target.checked);
        });
        
        document.getElementById('llmEnabled').addEventListener('change', (e) => {
            this.toggleLLMConfig(e.target.checked);
        });
        
        // 清空数据按钮事件
        document.getElementById('clearDataBtn').addEventListener('click', () => this.clearAllData());
        
        // 清空API密钥按钮事件
        document.getElementById('clearApiKeysBtn').addEventListener('click', () => this.clearAllApiKeys());
        
        // 文件拖拽上传
        this.initDragAndDrop();
        
        // 导航栏滚动效果
        this.initNavbarScroll();
    }

    initDragAndDrop() {
        const dragDropArea = document.querySelector('.drag-drop-area');
        
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dragDropArea.addEventListener(eventName, this.preventDefaults, false);
        });
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dragDropArea.addEventListener(eventName, () => {
                dragDropArea.classList.add('drag-over');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dragDropArea.addEventListener(eventName, () => {
                dragDropArea.classList.remove('drag-over');
            }, false);
        });
        
        dragDropArea.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                // 创建新的文件输入来处理拖拽的文件
                const fileInput = document.getElementById('fileInput');
                if (fileInput) {
                    fileInput.files = files;
                    this.handleFileSelection({ target: { files: files } });
                } else {
                    // 如果文件输入不存在，直接处理上传
                    this.handleDraggedFiles(files);
                }
            }
        }, false);
    }

    handleDraggedFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            const dragDropArea = document.querySelector('.drag-drop-area');
            const dragDropContent = document.querySelector('.drag-drop-content');
            
            // 更新显示
            dragDropContent.innerHTML = `
                <i class="bi bi-check-circle-fill text-success" style="font-size: 3rem; margin-bottom: 1rem;"></i>
                <h6 class="text-success">文件已选择</h6>
                <p class="text-muted mb-3">${file.name}</p>
                <p class="text-muted small">大小: ${this.formatFileSize(file.size)}</p>
                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="app.clearFileSelection()">
                    <i class="bi bi-x-circle me-1"></i>
                    重新选择
                </button>
            `;
            
            dragDropArea.classList.add('file-selected');
            this.showToast(`已选择文件: ${file.name}`, 'success');
            
            // 存储文件以供上传使用
            this.selectedFile = file;
        }
    }

    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    handleFileSelection(e) {
        const files = e.target.files;
        const dragDropArea = document.querySelector('.drag-drop-area');
        const dragDropContent = document.querySelector('.drag-drop-content');
        
        if (files && files.length > 0) {
            const file = files[0];
            
            // 存储选择的文件
            this.selectedFile = file;
            
            // 更新拖拽区域显示
            dragDropContent.innerHTML = `
                <i class="bi bi-check-circle-fill text-success" style="font-size: 3rem; margin-bottom: 1rem;"></i>
                <h6 class="text-success">文件已选择</h6>
                <p class="text-muted mb-3">${file.name}</p>
                <p class="text-muted small">大小: ${this.formatFileSize(file.size)}</p>
                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="app.clearFileSelection()">
                    <i class="bi bi-x-circle me-1"></i>
                    重新选择
                </button>
            `;
            
            // 添加成功样式
            dragDropArea.classList.add('file-selected');
            
            // 显示成功提示
            this.showToast(`已选择文件: ${file.name}`, 'success');
        }
    }

    clearFileSelection() {
        const fileInput = document.getElementById('fileInput');
        const dragDropArea = document.querySelector('.drag-drop-area');
        const dragDropContent = document.querySelector('.drag-drop-content');
        
        // 清空文件输入和存储的文件
        if (fileInput) {
            fileInput.value = '';
        }
        this.selectedFile = null;
        
        // 恢复原始显示
        dragDropContent.innerHTML = `
            <i class="bi bi-cloud-upload drag-drop-icon"></i>
            <h6>拖拽文件到此处</h6>
            <p class="text-muted mb-3">或者点击选择文件</p>
            <input type="file" class="form-control d-none" id="fileInput" accept=".txt">
            <button type="button" class="btn btn-outline-primary" onclick="document.getElementById('fileInput').click()">
                <i class="bi bi-folder2-open me-2"></i>
                选择文件
            </button>
        `;
        
        // 移除选择样式
        dragDropArea.classList.remove('file-selected');
        
        // 重新绑定事件
        document.getElementById('fileInput').addEventListener('change', (e) => this.handleFileSelection(e));
    }

    initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    initNavbarScroll() {
        window.addEventListener('scroll', () => {
            const navbar = document.querySelector('.navbar');
            if (window.scrollY > 50) {
                navbar.style.background = 'rgba(255, 255, 255, 0.98)';
            } else {
                navbar.style.background = 'rgba(255, 255, 255, 0.95)';
            }
        });
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const data = await response.json();
            
            if (data.success) {
                this.config = data.config;
                this.updateConfigUI();
            } else {
                this.showToast('加载配置失败: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('加载配置失败:', error);
            this.showToast('加载配置失败', 'error');
        }
    }

    async loadTemplates() {
        try {
            const response = await fetch('/api/templates');
            const data = await response.json();
            
            if (data.success) {
                this.updateTemplateOptions(data.templates);
            }
        } catch (error) {
            console.error('加载模板失败:', error);
        }
    }

    updateTemplateOptions(templates) {
        const select = document.getElementById('promptType');
        select.innerHTML = '';
        
        templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.type;
            option.textContent = template.name;
            option.title = template.description;
            select.appendChild(option);
        });
    }

    updateConfigUI() {
        if (!this.config) return;
        
        // 期刊指标配置
        const journalMetrics = this.config.journal_metrics || {};
        document.getElementById('journalMetricsEnabled').checked = journalMetrics.enabled !== false;
        
        if (this.config.easyscholar_api_key) {
            document.getElementById('easyscholarApiKey').value = this.config.easyscholar_api_key;
        }
        
        // 指标类型
        const metricsToFetch = journalMetrics.metrics_to_fetch || [];
        const allMetricCheckboxes = document.querySelectorAll('input[name="journalMetrics"]');
        allMetricCheckboxes.forEach(checkbox => {
            checkbox.checked = metricsToFetch.includes(checkbox.value);
        });
        
        // LLM配置
        const llm = this.config.llm || {};
        document.getElementById('llmEnabled').checked = llm.enabled !== false;
        document.getElementById('llmType').value = llm.type || 'siliconflow';
        
        // API密钥配置
        this.updateApiKeyField(llm.type || 'siliconflow', llm);
        
        // 硅基流动模型配置
        if (llm.siliconflow_model) {
            const modelSelect = document.getElementById('siliconflowModel');
            const customModelInput = document.getElementById('customSiliconflowModel');
            const predefinedModels = ['Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen3-8B', 'THUDM/GLM-Z1-9B-0414', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B'];
            
            if (predefinedModels.includes(llm.siliconflow_model)) {
                modelSelect.value = llm.siliconflow_model;
            } else {
                modelSelect.value = 'custom';
                customModelInput.value = llm.siliconflow_model;
                customModelInput.style.display = 'block';
            }
        }
        
        // 硅基流动限流配置
        document.getElementById('siliconflowRpm').value = llm.siliconflow_rpm || 1000;
        document.getElementById('siliconflowTpm').value = llm.siliconflow_tpm || 50000;
        
        // 模型参数配置
        const modelParams = llm.model_parameters || {};
        document.getElementById('maxTokens').value = modelParams.max_tokens || 4096;
        document.getElementById('temperature').value = modelParams.temperature || 0.7;
        document.getElementById('topP').value = modelParams.top_p || 0.9;
        
        // 处理配置
        const processing = this.config.processing || {};
        document.getElementById('batchSize').value = processing.batch_size || 16;
        document.getElementById('maxWorkers').value = processing.max_workers || 4;
        
        // 输出配置
        const output = this.config.output || {};
        document.getElementById('separateSheets').checked = output.separate_sheets !== false;
        
        // 提示词配置
        const prompt = this.config.prompt || {};
        if (prompt.default_type) {
            document.getElementById('promptType').value = prompt.default_type;
        }
        
        this.toggleJournalMetricsConfig(journalMetrics.enabled !== false);
        
        // 为所有期刊指标复选框添加事件监听器
        this.addMetricsChangeListeners();
        this.toggleLLMConfig(llm.enabled !== false);
        
        // 添加LLM相关事件监听器
        this.addLLMEventListeners();
    }

    toggleJournalMetricsConfig(enabled) {
        const configDiv = document.getElementById('journalMetricsConfig');
        configDiv.style.display = enabled ? 'block' : 'none';
    }

    toggleLLMConfig(enabled) {
        const configDiv = document.getElementById('llmConfig');
        configDiv.style.display = enabled ? 'block' : 'none';
    }
    
    updateApiKeyField(llmType, llmConfig) {
        const apiKeyInput = document.getElementById('llmApiKey');
        const validateBtn = document.getElementById('validateApiKeyBtn');
        const helpText = document.getElementById('apiKeyHelp');
        const siliconflowModelConfig = document.getElementById('siliconflowModelConfig');
        const baseUrlConfig = document.getElementById('baseUrlConfig');
        const baseUrlInput = document.getElementById('llmBaseUrl');
        const baseUrlHelp = document.getElementById('baseUrlHelp');
        
        // 根据LLM类型设置API密钥值
        let apiKey = '';
        let helpMessage = '';
        let baseUrl = '';
        let baseUrlHelpMessage = '';
        
        switch(llmType) {
            case 'siliconflow':
                apiKey = llmConfig.siliconflow_api_key || '';
                helpMessage = '请输入硅基流动API密钥，<a href="https://cloud.siliconflow.cn/account/ak" target="_blank">点击获取API密钥</a>';
                validateBtn.style.display = 'block';
                siliconflowModelConfig.style.display = 'block';
                baseUrlConfig.style.display = 'none';
                break;
            case 'vllm':
                apiKey = llmConfig.vllm_api_key || '';
                helpMessage = '请输入VLLM API密钥';
                baseUrl = llmConfig.vllm_api_url || 'http://127.0.0.1:8000/v1/chat/completions';
                baseUrlHelpMessage = '请输入VLLM服务的API地址';
                validateBtn.style.display = 'none';
                siliconflowModelConfig.style.display = 'none';
                baseUrlConfig.style.display = 'block';
                break;
            case 'ollama':
                apiKey = llmConfig.ollama_api_key || '';
                helpMessage = '请输入Ollama API密钥';
                baseUrl = llmConfig.ollama_api_url || 'http://localhost:11434/api';
                baseUrlHelpMessage = '请输入Ollama服务的API地址';
                validateBtn.style.display = 'none';
                siliconflowModelConfig.style.display = 'none';
                baseUrlConfig.style.display = 'block';
                break;
        }
        
        apiKeyInput.value = apiKey;
        helpText.innerHTML = helpMessage;
        
        if (baseUrlConfig.style.display === 'block') {
            baseUrlInput.value = baseUrl;
            baseUrlHelp.textContent = baseUrlHelpMessage;
        }
    }
    
    addLLMEventListeners() {
        const llmTypeSelect = document.getElementById('llmType');
        const siliconflowModelSelect = document.getElementById('siliconflowModel');
        const customModelInput = document.getElementById('customSiliconflowModel');
        const validateBtn = document.getElementById('validateApiKeyBtn');
        
        // LLM类型变化事件
        llmTypeSelect.addEventListener('change', (e) => {
            const llmType = e.target.value;
            this.updateApiKeyField(llmType, this.config.llm || {});
        });
        
        // 硅基流动模型选择事件
        siliconflowModelSelect.addEventListener('change', (e) => {
            const isCustom = e.target.value === 'custom';
            customModelInput.style.display = isCustom ? 'block' : 'none';
            if (!isCustom) {
                customModelInput.value = '';
            }
        });
        
        // API密钥验证按钮事件
        validateBtn.addEventListener('click', () => {
            this.validateSiliconFlowApiKey();
        });
    }
    
    async validateSiliconFlowApiKey() {
        const apiKeyInput = document.getElementById('llmApiKey');
        const validateBtn = document.getElementById('validateApiKeyBtn');
        const apiKey = apiKeyInput.value.trim();
        
        if (!apiKey) {
            this.showToast('请先输入API密钥', 'warning');
            return;
        }
        
        // 禁用按钮并显示加载状态
        validateBtn.disabled = true;
        validateBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 验证中...';
        
        try {
            const response = await fetch('https://api.siliconflow.cn/v1/user/info', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${apiKey}`
                }
            });
            
            const data = await response.json();
            
            if (data.code === 20000 && data.status === true) {
                this.showToast(`API密钥验证成功！用户: ${data.data.name}, 余额: ${data.data.totalBalance}`, 'success');
            } else {
                this.showToast('API密钥验证失败，请检查密钥是否正确', 'error');
            }
        } catch (error) {
            console.error('API密钥验证错误:', error);
            this.showToast('API密钥验证失败，请检查网络连接或密钥是否正确', 'error');
        } finally {
            // 恢复按钮状态
            validateBtn.disabled = false;
            validateBtn.innerHTML = '<i class="bi bi-check-circle"></i> 验证';
        }
    }

    async uploadFile() {
        const fileInput = document.getElementById('fileInput');
        const sourceType = document.getElementById('sourceType').value;
        
        // 优先使用存储的文件，然后是文件输入的文件
        let file = this.selectedFile;
        if (!file && fileInput && fileInput.files && fileInput.files.length > 0) {
            file = fileInput.files[0];
        }
        
        if (!file) {
            this.showToast('请选择要上传的文件', 'warning');
            return;
        }
        
        if (!file.name.toLowerCase().endsWith('.txt')) {
            this.showToast('请选择.txt格式的文件', 'error');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source_type', sourceType);
        
        try {
            this.showLoading(true);
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.uploadedFiles.push({
                    filename: data.filename,
                    filepath: data.filepath,
                    source_type: data.source_type,
                    original_name: file.name,
                    size: file.size
                });
                
                this.updateUploadedFilesList();
                this.showToast('文件上传成功', 'success');
                
                // 清空文件选择状态
                this.clearFileSelection();
            } else {
                this.showToast('上传失败: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('上传失败:', error);
            this.showToast('上传失败', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    updateUploadedFilesList() {
        const container = document.getElementById('uploadedFiles');
        
        if (this.uploadedFiles.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-inbox empty-icon"></i>
                    <p class="empty-text">暂无上传文件</p>
                    <small class="text-muted">上传文件后将在此处显示</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div class="files-header">
                <h6 class="mb-0"><i class="bi bi-files me-2"></i>已上传文件 (${this.uploadedFiles.length})</h6>
                <button class="btn btn-sm btn-outline-secondary" onclick="app.clearAllFiles()">
                    <i class="bi bi-trash3 me-1"></i>清空全部
                </button>
            </div>
            <div class="files-list">
                ${this.uploadedFiles.map((file, index) => `
                    <div class="file-item" data-index="${index}">
                        <div class="file-icon-wrapper">
                            <div class="file-icon ${file.source_type}">
                                <i class="bi bi-file-earmark-text"></i>
                            </div>
                            <div class="source-badge ${file.source_type}">
                                ${file.source_type.toUpperCase()}
                            </div>
                        </div>
                        <div class="file-details">
                            <div class="file-name" title="${file.original_name}">${file.original_name}</div>
                            <div class="file-meta">
                                <span class="file-size">
                                    <i class="bi bi-hdd me-1"></i>${this.formatFileSize(file.size)}
                                </span>
                                <span class="upload-time">
                                    <i class="bi bi-clock me-1"></i>刚刚上传
                                </span>
                            </div>
                        </div>
                        <div class="file-actions">
                            <button class="btn btn-sm btn-outline-primary" onclick="app.previewFile(${index})" title="预览">
                                <i class="bi bi-eye"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="app.removeFile(${index})" title="删除">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    removeFile(index) {
        const fileName = this.uploadedFiles[index].original_name;
        this.uploadedFiles.splice(index, 1);
        this.updateUploadedFilesList();
        this.showToast(`已移除文件: ${fileName}`, 'info');
    }

    clearAllFiles() {
        if (this.uploadedFiles.length === 0) return;
        
        const count = this.uploadedFiles.length;
        this.uploadedFiles = [];
        this.updateUploadedFilesList();
        this.showToast(`已清空 ${count} 个文件`, 'info');
    }

    previewFile(index) {
        const file = this.uploadedFiles[index];
        this.showToast(`预览功能开发中: ${file.original_name}`, 'info');
        // TODO: 实现文件预览功能
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async processData() {
        if (this.uploadedFiles.length === 0) {
            this.showToast('请先上传数据文件', 'warning');
            return;
        }
        
        // 收集配置
        const config = this.collectConfig();
        
        try {
            const response = await fetch('/api/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    sources: this.uploadedFiles,
                    config: config
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('数据处理已开始', 'success');
                // 初始化时间跟踪
                this.processStartTime = Date.now();
                this.lastProgressUpdate = Date.now();
                this.progressHistory = [];
                this.startStatusPolling();
                this.showProcessStatus(true);
            } else {
                this.showToast('启动处理失败: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('处理失败:', error);
            this.showToast('处理失败', 'error');
        }
    }

    collectConfig() {
        return {
            journal_metrics: {
                enabled: document.getElementById('journalMetricsEnabled').checked,
                metrics_to_fetch: this.getSelectedMetrics()
            },
            llm: {
                enabled: document.getElementById('llmEnabled').checked,
                type: document.getElementById('llmType').value,
                ...this.collectLLMConfig()
            },
            prompt: {
                default_type: document.getElementById('promptType').value
            },
            processing: {
                batch_size: parseInt(document.getElementById('batchSize').value),
                max_workers: parseInt(document.getElementById('maxWorkers').value)
            },
            output: {
                separate_sheets: document.getElementById('separateSheets').checked
            },
            easyscholar_api_key: document.getElementById('easyscholarApiKey').value
        };
    }

    getSelectedMetrics() {
        const metrics = [];
        const checkboxes = document.querySelectorAll('input[name="journalMetrics"]:checked');
        checkboxes.forEach(checkbox => {
            metrics.push(checkbox.value);
        });
        return metrics;
    }
    
    collectLLMConfig() {
        const llmType = document.getElementById('llmType').value;
        const apiKey = document.getElementById('llmApiKey').value;
        const baseUrl = document.getElementById('llmBaseUrl').value;
        const config = {};
        
        // 根据LLM类型设置对应的API密钥和Base URL
        switch(llmType) {
            case 'siliconflow':
                config.siliconflow_api_key = apiKey;
                // 硅基流动模型配置
                const modelSelect = document.getElementById('siliconflowModel');
                const customModelInput = document.getElementById('customSiliconflowModel');
                if (modelSelect.value === 'custom') {
                    config.siliconflow_model = customModelInput.value;
                } else {
                    config.siliconflow_model = modelSelect.value;
                }
                // 硅基流动限流配置
                config.siliconflow_rpm = parseInt(document.getElementById('siliconflowRpm').value);
                config.siliconflow_tpm = parseInt(document.getElementById('siliconflowTpm').value);
                break;
            case 'vllm':
                config.vllm_api_key = apiKey;
                config.vllm_api_url = baseUrl || 'http://127.0.0.1:8000/v1/chat/completions';
                break;
            case 'ollama':
                config.ollama_api_key = apiKey;
                config.ollama_api_url = baseUrl || 'http://localhost:11434/api';
                break;
        }
        
        // 模型参数配置
        config.model_parameters = {
            max_tokens: parseInt(document.getElementById('maxTokens').value),
            temperature: parseFloat(document.getElementById('temperature').value),
            top_p: parseFloat(document.getElementById('topP').value)
        };
        
        return config;
    }

    async saveConfig() {
        try {
            const config = this.collectConfig();
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
            
            const data = await response.json();
            if (data.success) {
                this.config = config;
                this.showToast('配置保存成功', 'success');
            } else {
                this.showToast('配置保存失败: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showToast('保存配置失败', 'error');
        }
    }

    addMetricsChangeListeners() {
        const metricCheckboxes = document.querySelectorAll('input[name="journalMetrics"]');
        metricCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                // 延迟保存，避免频繁请求
                clearTimeout(this.saveConfigTimeout);
                this.saveConfigTimeout = setTimeout(() => {
                    this.saveConfig();
                }, 500);
            });
        });
    }

    showProcessStatus(show) {
        const statusDiv = document.getElementById('processStatus');
        const processBtn = document.getElementById('processBtn');
        
        statusDiv.style.display = show ? 'block' : 'none';
        processBtn.disabled = show;
        
        if (show) {
            processBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 处理中...';
        } else {
            processBtn.innerHTML = '<i class="bi bi-play-circle"></i> 开始处理数据';
        }
    }

    startStatusPolling() {
        this.processingInterval = setInterval(() => {
            this.checkProcessStatus();
        }, 2000);
    }

    stopStatusPolling() {
        if (this.processingInterval) {
            clearInterval(this.processingInterval);
            this.processingInterval = null;
        }
    }

    async checkProcessStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.success) {
                const status = data.status;
                this.updateProcessStatus(status);
                
                if (!status.is_processing) {
                    this.stopStatusPolling();
                    this.showProcessStatus(false);
                    
                    if (status.error) {
                        this.showToast('处理失败: ' + status.error, 'error');
                    } else if (status.result_file) {
                        this.showProcessResult(status);
                    }
                }
            }
        } catch (error) {
            console.error('检查状态失败:', error);
        }
    }

    updateProcessStatus(status) {
        const progressBar = document.getElementById('progressBar');
        const statusMessage = document.getElementById('statusMessage');
        
        progressBar.style.width = status.progress + '%';
        progressBar.textContent = status.progress.toFixed(2) + '%';
        
        let displayMessage = status.message;
        
        // 添加详细的处理信息 - 显示当前阶段的处理状态
        const processed = status.processed_records || 0;
        const remaining = status.remaining_records || 0;
        const total = processed + remaining;
        
        if (total > 0) {
            displayMessage += ` [已处理: ${processed}/${total}, 剩余: ${remaining}]`;
        }
        
        if (status.progress > 0 && status.progress < 100) {
            const estimatedTime = this.calculateEstimatedTime(status.progress);
            if (estimatedTime) {
                displayMessage += ` (预计剩余时间: ${estimatedTime})`;
            }
        }
        
        statusMessage.textContent = displayMessage;
        
        if (status.progress === 100) {
            progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
            progressBar.classList.add('bg-success');
        }
        
        this.updateProgressHistory(status.progress);
    }
    
    updateProgressHistory(progress) {
        const now = Date.now();
        this.progressHistory.push({
            progress: progress,
            timestamp: now
        });
        
        // 只保留最近的10个进度点
        if (this.progressHistory.length > 10) {
            this.progressHistory.shift();
        }
    }
    
    calculateEstimatedTime(currentProgress) {
        if (!this.processStartTime || currentProgress <= 0 || this.progressHistory.length < 2) {
            return null;
        }
        
        const now = Date.now();
        const elapsedTime = now - this.processStartTime;
        
        // 使用最近的进度变化来计算速度
        const recentHistory = this.progressHistory.slice(-5); // 最近5个点
        if (recentHistory.length < 2) {
            return null;
        }
        
        const firstPoint = recentHistory[0];
        const lastPoint = recentHistory[recentHistory.length - 1];
        
        const progressDiff = lastPoint.progress - firstPoint.progress;
        const timeDiff = lastPoint.timestamp - firstPoint.timestamp;
        
        if (progressDiff <= 0 || timeDiff <= 0) {
            return null;
        }
        
        // 计算每毫秒的进度
        const progressPerMs = progressDiff / timeDiff;
        
        // 计算剩余进度
        const remainingProgress = 100 - currentProgress;
        
        // 计算预计剩余时间（毫秒）
        const estimatedRemainingMs = remainingProgress / progressPerMs;
        
        // 转换为可读格式
        return this.formatTime(estimatedRemainingMs);
    }
    
    formatTime(milliseconds) {
        const seconds = Math.floor(milliseconds / 1000);
        
        if (seconds < 60) {
            return `${seconds}秒`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return `${minutes}分${remainingSeconds}秒`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const remainingMinutes = Math.floor((seconds % 3600) / 60);
            return `${hours}小时${remainingMinutes}分钟`;
        }
    }

    showProcessResult(status) {
        const resultContent = document.getElementById('resultContent');
        
        resultContent.innerHTML = `
            <div class="result-success">
                <i class="bi bi-check-circle-fill"></i>
                <h5 class="text-success mb-3">处理完成！</h5>
                <p class="mb-3">${status.message}</p>
                <a href="/api/download/${status.result_file}" class="btn btn-success btn-lg">
                    <i class="bi bi-download"></i>
                    下载结果文件
                </a>
            </div>
        `;
        
        // 滚动到结果区域
        document.getElementById('results').scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
        
        this.showToast('数据处理完成！', 'success');
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        overlay.style.display = show ? 'flex' : 'none';
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const toastBody = document.getElementById('toastBody');
        const toastHeader = toast.querySelector('.toast-header');
        
        // 设置图标和颜色
        const icons = {
            success: 'bi-check-circle text-success',
            error: 'bi-exclamation-circle text-danger',
            warning: 'bi-exclamation-triangle text-warning',
            info: 'bi-info-circle text-primary'
        };
        
        const icon = toastHeader.querySelector('i');
        icon.className = `${icons[type] || icons.info} me-2`;
        
        toastBody.textContent = message;
        
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    }
    
    clearAllData() {
        if (!confirm('确定要清空data目录下的所有文件吗？此操作不可撤销！')) {
            return;
        }
        
        this.showLoading(true);
        
        $.ajax({
            url: '/api/clear-data',
            method: 'POST'
        })
        .done((response) => {
            this.showToast('数据文件清空成功', 'success');
        })
        .fail((xhr) => {
            this.showToast('清空数据文件失败: ' + (xhr.responseJSON?.error || '未知错误'), 'error');
        })
        .always(() => {
            this.showLoading(false);
        });
    }
    
    clearAllApiKeys() {
        if (!confirm('确定要清空所有API密钥信息吗？此操作不可撤销！')) {
            return;
        }
        
        this.showLoading(true);
        
        $.ajax({
            url: '/api/clear-api-keys',
            method: 'POST'
        })
        .done((response) => {
            this.showToast('API密钥清空成功', 'success');
            // 清空前端显示的API密钥
            document.getElementById('llmApiKey').value = '';
            document.getElementById('easyScholarApiKey').value = '';
        })
        .fail((xhr) => {
            this.showToast('清空API密钥失败: ' + (xhr.responseJSON?.error || '未知错误'), 'error');
        })
        .always(() => {
            this.showLoading(false);
        });
    }
}

// 期刊指标批量操作函数
function selectAllMetrics() {
    const checkboxes = document.querySelectorAll('[id^="metric_"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
    });
    app.showToast('已选择所有指标', 'success');
}

function clearAllMetrics() {
    const checkboxes = document.querySelectorAll('[id^="metric_"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });
    app.showToast('已清空所有指标', 'info');
}

function selectCommonMetrics() {
    // 先清空所有选择
    clearAllMetrics();
    
    // 选择常用指标
    const commonMetrics = [
        'metric_sciif',    // SCI影响因子-JCR
        'metric_sci',      // SCI分区-JCR
        'metric_sciUp',    // SCI升级版分区-中科院
    ];
    
    commonMetrics.forEach(metricId => {
        const checkbox = document.getElementById(metricId);
        if (checkbox) {
            checkbox.checked = true;
        }
    });
    
    app.showToast('已选择常用指标', 'success');
}

// 标签页切换功能
function switchTab(tabId) {
    // 隐藏所有标签页内容
    const allTabs = document.querySelectorAll('.tab-content');
    allTabs.forEach(tab => {
        tab.classList.remove('active');
    });
    
    // 移除所有标签按钮的激活状态
    const allButtons = document.querySelectorAll('.tab-button');
    allButtons.forEach(button => {
        button.classList.remove('active');
    });
    
    // 显示选中的标签页内容
    const selectedTab = document.getElementById(tabId);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }
    
    // 激活对应的标签按钮
    const selectedButton = document.querySelector(`[onclick="switchTab('${tabId}')"]`);
    if (selectedButton) {
        selectedButton.classList.add('active');
    }
}

// 初始化应用
const app = new ScholarMindApp();

// 页面加载完成后初始化
$(document).ready(function() {
    loadConfig();
    loadTemplates();
    initializeEventHandlers();
    initializeTemplateEditor();
});

// 提示词模板编辑功能
let currentTemplate = null;
let templateList = [];

// 初始化模板编辑器
function initializeTemplateEditor() {
    // 编辑模板按钮 - 打开模态框 (使用事件委托)
    $(document).on('click', '#editTemplateBtn', function() {
        console.log('编辑按钮被点击'); // 调试日志
        $('#templateModal').modal('show');
        loadTemplateList();
    });
    
    // 新建模板按钮
    $(document).on('click', '#createTemplateBtn', function() {
        createNewTemplate();
    });
    
    // 保存模板按钮
    $(document).on('click', '#saveTemplateBtn', function() {
        saveTemplate();
    });
    
    // 删除模板按钮
    $(document).on('click', '#deleteTemplateBtn', function() {
        deleteTemplate();
    });
    
    // 添加字段按钮
    $(document).on('click', '#addFieldBtn', function() {
        addOutputField();
    });
    
    // 模板类型输入验证
    $('#templateType').on('input', function() {
        const value = $(this).val();
        const sanitized = value.replace(/[^a-zA-Z0-9_]/g, '');
        if (value !== sanitized) {
            $(this).val(sanitized);
        }
    });
    
    // 模态框关闭时重新加载提示词模板选择框
    $('#templateModal').on('hidden.bs.modal', function() {
        loadTemplates(); // 重新加载模板选择框
    });
}

// 加载模板列表
function loadTemplateList() {
    $.get('/api/templates')
        .done(function(data) {
            templateList = data;
            renderTemplateList();
        })
        .fail(function(xhr) {
            showAlert('加载模板列表失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
        });
}

// 渲染模板列表
function renderTemplateList() {
    const listContainer = $('#templateList');
    listContainer.empty();
    
    templateList.forEach(function(template) {
        const listItem = $(`
            <a href="#" class="list-group-item list-group-item-action" data-template-type="${template.type}">
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">${template.name}</h6>
                    <small class="text-muted">${template.type}</small>
                </div>
                <p class="mb-1 text-muted small">${template.description}</p>
            </a>
        `);
        
        listContainer.append(listItem);
    });
    
    // 使用事件委托处理模板列表项点击
    $(document).off('click', '#templateList .list-group-item').on('click', '#templateList .list-group-item', function(e) {
        e.preventDefault();
        const templateType = $(this).data('template-type');
        loadTemplate(templateType);
    });
}

// 加载单个模板
function loadTemplate(templateType) {
    $.get(`/api/templates/${templateType}`)
        .done(function(data) {
            currentTemplate = data;
            renderTemplateEditor(data);
            
            // 更新列表选中状态
            $('#templateList .list-group-item').removeClass('active');
            $(`#templateList .list-group-item[data-template-type="${templateType}"]`).addClass('active');
        })
        .fail(function(xhr) {
            showAlert('加载模板失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
        });
}

// 渲染模板编辑器
function renderTemplateEditor(template) {
    $('#emptyState').hide();
    $('#templateEditor').show();
    
    // 设置标题
    $('#editorTitle').text(`编辑模板: ${template.name}`);
    
    // 填充基本信息
    $('#templateType').val(template.type);
    $('#templateName').val(template.name);
    $('#templateDescription').val(template.description || '');
    $('#systemPrompt').val(template.system);
    $('#userTemplate').val(template.user_template);
    
    // 渲染输出字段
    renderOutputFields(template.fields || [], template.default_values || {});
    
    // 如果是系统模板，禁用类型编辑
    if (template.type === 'medical' || template.type === 'custom') {
        $('#templateType').prop('readonly', true);
        $('#deleteTemplateBtn').hide();
    } else {
        $('#templateType').prop('readonly', false);
        $('#deleteTemplateBtn').show();
    }
}

// 渲染输出字段
function renderOutputFields(fields, defaultValues) {
    const container = $('#fieldsContainer');
    container.empty();
    
    fields.forEach(function(field, index) {
        addOutputFieldRow(field, defaultValues[field] || '', index);
    });
}

// 添加输出字段行
function addOutputFieldRow(fieldName = '', defaultValue = '', index = null) {
    const container = $('#fieldsContainer');
    const fieldIndex = index !== null ? index : container.children().length;
    
    const fieldRow = $(`
        <div class="row mb-2 field-row" data-index="${fieldIndex}">
            <div class="col-md-4">
                <input type="text" class="form-control field-name" placeholder="字段名" value="${fieldName}">
            </div>
            <div class="col-md-6">
                <input type="text" class="form-control field-default" placeholder="默认值" value="${defaultValue}">
            </div>
            <div class="col-md-2">
                <button type="button" class="btn btn-outline-danger btn-sm remove-field">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `);
    
    // 删除字段按钮
    fieldRow.find('.remove-field').click(function() {
        fieldRow.remove();
    });
    
    container.append(fieldRow);
}

// 添加新的输出字段
function addOutputField() {
    addOutputFieldRow();
}

// 创建新模板
function createNewTemplate() {
    $.post('/api/templates', {
        type: 'new_template_' + Date.now(),
        name: '新模板',
        description: '新创建的模板',
        system: '你是一个专业的学术文献分析助手。',
        user_template: '请分析以下文献摘要：\n\n{abstract}\n\n请按照以下格式输出分析结果。',
        fields: ['summary'],
        default_values: {'summary': '文献摘要分析'}
    })
    .done(function(data) {
        showAlert('新模板创建成功', 'success');
        loadTemplateList();
        loadTemplate(data.type);
        // 更新主页面的模板选择框
        loadTemplates();
    })
    .fail(function(xhr) {
        showAlert('创建模板失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

// 保存模板
function saveTemplate() {
    if (!currentTemplate) {
        showAlert('请先选择一个模板', 'warning');
        return;
    }
    
    // 收集表单数据
    const templateData = {
        type: $('#templateType').val().trim(),
        name: $('#templateName').val().trim(),
        description: $('#templateDescription').val().trim(),
        system: $('#systemPrompt').val().trim(),
        user_template: $('#userTemplate').val().trim(),
        fields: [],
        default_values: {}
    };
    
    // 验证必填字段
    if (!templateData.type || !templateData.name || !templateData.system || !templateData.user_template) {
        showAlert('请填写所有必填字段', 'warning');
        return;
    }
    
    // 验证用户模板包含{abstract}
    if (!templateData.user_template.includes('{abstract}')) {
        showAlert('用户提示词模板必须包含 {abstract} 占位符', 'warning');
        return;
    }
    
    // 收集输出字段
    $('.field-row').each(function() {
        const fieldName = $(this).find('.field-name').val().trim();
        const defaultValue = $(this).find('.field-default').val().trim();
        
        if (fieldName) {
            templateData.fields.push(fieldName);
            templateData.default_values[fieldName] = defaultValue;
        }
    });
    
    // 保存模板
    $.ajax({
        url: `/api/templates/${currentTemplate.type}`,
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(templateData)
    })
    .done(function(data) {
        showAlert('模板保存成功', 'success');
        const oldType = currentTemplate.type;
        currentTemplate = templateData;
        loadTemplateList();
        
        // 如果类型改变了，重新加载
        if (templateData.type !== oldType) {
            loadTemplate(templateData.type);
        }
        
        // 更新主页面的模板选择框
        loadTemplates();
    })
    .fail(function(xhr) {
        showAlert('保存模板失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

// 删除模板
function deleteTemplate() {
    if (!currentTemplate) {
        showAlert('请先选择一个模板', 'warning');
        return;
    }
    
    if (currentTemplate.type === 'medical' || currentTemplate.type === 'custom') {
        showAlert('系统模板不能删除', 'warning');
        return;
    }
    
    if (!confirm(`确定要删除模板 "${currentTemplate.name}" 吗？此操作不可撤销。`)) {
        return;
    }
    
    $.ajax({
        url: `/api/templates/${currentTemplate.type}`,
        method: 'DELETE'
    })
    .done(function() {
        showAlert('模板删除成功', 'success');
        currentTemplate = null;
        $('#templateEditor').hide();
        $('#emptyState').show();
        $('#templateList .list-group-item').removeClass('active');
        loadTemplateList();
        // 更新主页面的模板选择框
        loadTemplates();
    })
    .fail(function(xhr) {
        showAlert('删除模板失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

// 添加一些CSS动画类
const style = document.createElement('style');
style.textContent = `
    .fade-in {
        animation: fadeIn 0.5s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .processing {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
    
    .field-row {
        border-left: 3px solid #e9ecef;
        padding-left: 10px;
        margin-left: 5px;
    }
    
    .field-row:hover {
        border-left-color: #007bff;
        background-color: #f8f9fa;
    }
    
    .drag-over {
        border-color: var(--primary-color) !important;
        background: rgba(37, 99, 235, 0.1) !important;
        transform: scale(1.02);
    }
    
    .file-item {
        animation: fadeInUp 0.3s ease-out;
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);