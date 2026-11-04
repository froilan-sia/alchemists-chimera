# 🏗️ Coding Standards & Development Guidelines
## For The Alchemist's Chimera - Kiroween 2026 Project

---

## 📋 Overview

This steering file establishes coding standards, architectural patterns, and development workflows for the hybrid RAG engine project. These standards ensure consistency, maintainability, and adherence to best practices throughout the Kiroween hackathon development.

---

## 🐍 Python Standards

### General Principles
1. **PEP 8 Compliance**: All code must follow PEP 8 guidelines
2. **Type Hints**: Use Python type hints for all function signatures
3. **Docstrings**: Comprehensive docstrings for all modules, classes, and functions
4. **Imports**: Group imports (standard library, third-party, local) with blank lines

### Code Organization
```python
# Example structure
"""Module docstring explaining purpose."""

from typing import List, Optional, Dict, Any
import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ExampleClass(BaseModel):
    """Class docstring."""
    
    def example_method(self, param: str) -> Optional[str]:
        """Method docstring.
        
        Args:
            param: Description of parameter
            
        Returns:
            Description of return value
        """
        # Implementation
        pass
```

### Error Handling
- Use specific exceptions, not bare `except:` clauses
- Log errors with appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Provide meaningful error messages
- Use context managers for resource management

---

## 🏗️ Architectural Patterns

### Data Models
- Use Pydantic BaseModel for all data structures
- Define validation rules within models
- Use typing annotations for clarity
- Implement serialization/deserialization methods

### Component Design
1. **Single Responsibility**: Each module/class has one clear purpose
2. **Interface Segregation**: Define clean interfaces between components
3. **Dependency Injection**: Use dependency injection for testability
4. **Configuration Management**: Externalize configuration from code

### Graph-Vector Integration
```python
# Pattern for hybrid retrieval components
class HybridRetriever:
    """Base pattern for dual-engine retrieval."""
    
    def __init__(self, graph_store: GraphStore, vector_store: VectorStore):
        self.graph_store = graph_store
        self.vector_store = vector_store
    
    async def retrieve(self, query: QueryRequest) -> HybridResponse:
        """Execute hybrid retrieval."""
        # Parallel execution pattern
        graph_task = asyncio.create_task(self._graph_retrieval(query))
        vector_task = asyncio.create_task(self._vector_retrieval(query))
        
        graph_results, vector_results = await asyncio.gather(graph_task, vector_task)
        
        return self._fuse_results(graph_results, vector_results)
```

---

## 🧪 Testing Standards

### Test Structure
- Place tests in `/tests/` directory
- Use pytest as test framework
- Follow Arrange-Act-Assert pattern
- Use fixtures for common setup

### Test Coverage Goals
- Unit tests: 80%+ coverage
- Integration tests: Critical paths covered
- Performance tests: Benchmark key operations
- Edge cases: Handle error conditions

### Mocking Strategy
- Mock external dependencies (LLM, databases)
- Use dependency injection for testability
- Create test doubles for complex components
- Use pytest fixtures for shared test data

---

## 📝 Documentation Standards

### Code Documentation
- Module-level docstrings explaining purpose
- Class docstrings with examples
- Function/method docstrings with parameters and returns
- Inline comments for complex logic only

### API Documentation
- Use OpenAPI/Swagger for REST endpoints
- Include examples for all endpoints
- Document error responses
- Provide usage examples

### Project Documentation
- Keep README.md up to date
- Document architecture decisions
- Provide setup and deployment guides
- Include troubleshooting information

---

## 🔧 Development Workflow

### Git Practices
1. **Branch Strategy**: Feature branches from `main`
2. **Commit Messages**: Use conventional commits format
3. **Pull Requests**: Require review before merge
4. **Commit Frequency**: Small, focused commits

### Code Review Checklist
- [ ] Follows coding standards
- [ ] Includes tests
- [ ] Updates documentation
- [ ] Handles edge cases
- [ ] Performance considerations

### CI/CD Pipeline
- Automated testing on push
- Code quality checks
- Performance benchmarks
- Documentation generation

---

## 🎯 Performance Standards

### Latency Targets
- Query processing: < 5 seconds (P95)
- Retrieval operations: < 2 seconds
- LLM response: < 10 seconds
- Cold start: < 30 seconds

### Memory Usage
- Monitor memory consumption
- Implement connection pooling
- Use generators for large datasets
- Profile memory-intensive operations

### Optimization Guidelines
- Use async/await for I/O operations
- Implement caching where appropriate
- Batch operations when possible
- Monitor and optimize hot paths

---

## 🔒 Security Standards

### Input Validation
- Validate all user inputs
- Sanitize query parameters
- Implement rate limiting
- Use parameterized queries

### Data Protection
- No sensitive data in logs
- Secure configuration management
- Environment-specific secrets
- Audit logging for sensitive operations

### Dependency Security
- Regular dependency updates
- Security vulnerability scanning
- Pinned dependency versions
- Verified sources for all packages

---

## 📊 Quality Metrics

### Code Quality
- Cyclomatic complexity < 10
- Cognitive complexity < 15
- Maintainability index > 80
- No code duplication

### Test Quality
- Test coverage targets met
- No skipped tests
- Meaningful test names
- Independent test execution

### Documentation Quality
- All public APIs documented
- Examples provided
- Updated with code changes
- Clear and concise

---

## 🛠️ Tool Configuration

### Linting
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
```

### Testing Configuration
```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --cov=src
    --cov-report=term-missing
    --cov-report=html
```

---

## 🚀 Kiro-Specific Guidelines

### Spec-Driven Development
- Keep spec document updated
- Link implementation to spec tasks
- Use Kiro for code generation
- Document Kiro-assisted changes

### Steering File Usage
- Reference this file in development
- Update standards as needed
- Use for code review guidance
- Share with team members

### Agent Hook Integration
- Create hooks for common tasks
- Document hook purposes
- Test hook execution
- Monitor hook performance

---

*This steering file is part of the Kiroween 2026 submission for The Alchemist's Chimera.*  
*Last updated: November 4, 2026 | Version: 1.0.0*