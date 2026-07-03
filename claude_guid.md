# Claude Guide — FindMeApp

> AI Co-Creation Agreement v1.0

## 1. Code Style Conventions

### Language Preference
- Primary: **Python** / **C++**
- Format: 4-space indentation
- Naming convention: **camelCase**
- Comments: **English only**

### Python Specifics
```python
# Example: camelCase for functions and variables
def processUserData(inputData):
    """Process and validate user input."""
    processedData = []  # camelCase variable names
    for item in inputData:
        processedData.append(item.strip())
    return processedData
```

### C++ Specifics
```cpp
// Example: camelCase for variables and functions
void processUserData(const std::vector<std::string>& inputData) {
    std::vector<std::string> processedData;  // camelCase
    for (const auto& item : inputData) {
        processedData.push_back(item);
    }
}
```

---

## 2. Communication Agreement

### Code Submission Guidelines
- **Only provide changed sections**, not entire unchanged code
- Use **diff format** or **line numbers** to pinpoint modifications
- Example: `[Line 42-45]` or include context lines before/after

### Each Conversation
- Start with brief **context** and **goal**
- Example: "*Context: Working on user authentication module. Goal: Add email verification.*"

---

## 3. Project Structure Templates

### Python Project
```
project_name/
├── src/                    # Core source code
│   ├── main.py            # Project entry point
│   ├── modules/           # Feature modules
│   └── utils/             # Utility functions
├── tests/                 # Unit and integration tests
├── docs/                  # Project documentation
├── config/                # Configuration files
├── README.md              # Project overview
└── requirements.txt       # Python dependencies
```

### C++ Project
```
project_name/
├── src/                   # Source files (.cpp)
├── include/               # Header files (.h/.hpp)
├── tests/                 # Test code
├── build/                 # Build output directory
├── CMakeLists.txt         # Build configuration
├── docs/                  # Project documentation
└── README.md              # Project overview
```

---

## 4. Technology Stack Preferences

### Python Stack
- **Web Framework**: FastAPI
- **Data Processing**: Pandas
- **Testing**: Pytest
- **Code Formatting**: Black
- **Version Control**: Git
- **Editor**: VS Code
- **Containerization**: Docker

### C++ Stack
- **Build Tool**: CMake
- **Testing**: Google Test (GTest)
- **Logging**: Spdlog
- **JSON Processing**: nlohmann/json
- **Version Control**: Git
- **Editor**: VS Code
- **Containerization**: Docker

---

## 5. FindMeApp Specific

### Project Overview
> Define what FindMeApp does here.

### Tech Stack
- Language:
- Framework:
- Key dependencies:

### Development Setup
```bash
# Install dependencies
# ...

# Run locally
# ...
```

### Key Notes for Claude
- Important context or constraints:
- Things to avoid:
- Special considerations:


### 5.2 Playbook（协调层 - 灵活）
**定位**：灵活的任务编排和决策层

**职责**：
- 接收 Agent 的规划指令
- 分解复杂任务为多个步骤
- 根据上下文动态选择执行路径
- 处理异常情况和分支逻辑
- 协调多个 Script 的调用顺序

**约束**：
- 必须包含清晰的任务描述和目标
- 需要定义成功/失败的判断标准
- 应支持参数化配置
- 要有明确的输入输出定义
- 允许条件分支和循环逻辑

**示例场景**：
- 代码重构流程编排
- 多步骤测试执行计划
- 复杂部署流程管理

### 5.3 Script（执行层 - 确定）
**定位**：确定性的原子操作执行单元

**职责**：
- 执行具体的、单一的操作
- 保证幂等性和可重复性
- 返回明确的执行结果
- 处理基本的错误情况

**约束**：
- 每个 Script 只做一件事
- 必须有明确的输入参数验证
- 必须返回标准化的结果格式（成功/失败/输出）
- 不应包含复杂的业务逻辑
- 执行时间应该可预测
- 必须支持超时控制

**示例场景**：
- 运行单元测试
- 执行代码格式化
- 读取/写入配置文件
- 调用外部 API

### 5.4 反馈循环机制

**反馈循环1（内循环 - 自动纠错）**：
- Script 执行失败时自动重试
- 根据错误类型选择不同的 Script
- 在 Playbook 层面进行自动调整
- 无需人工介入的常规错误处理

**反馈循环2（外循环 - 人工干预）**：
- 遇到无法自动解决的问题时
- 向人类请求额外信息或决策
- 人类可以修改 Playbook 或 Script
- 人类可以直接介入执行流程

### 5.5 生产环境要求

**这个在生产环境下是非常重要的**：

1. **可观测性**：
   - 所有 Playbook 和 Script 执行必须有日志
   - 记录输入参数、执行时间、输出结果
   - 支持追踪完整的执行链路

2. **可靠性**：
   - Script 必须经过充分测试
   - Playbook 要有回滚机制
   - 关键操作需要确认步骤

3. **安全性**：
   - 敏感操作需要权限验证
   - 参数输入必须经过校验和清理
   - 避免执行不可信的代码

4. **可维护性**：
   - Playbook 和 Script 需要版本管理
   - 保持清晰的文档和注释
   - 定期审查和优化执行流程

