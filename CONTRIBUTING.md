
# Contributing 🚀

## Table of Contents

- [📝 Issue and merge request Guidelines](#contribution-guidelines)
- [🧪 Testing](#testing)
- [🚀 Deployment](#deployment)
- [📝 License](#license)
- [💬 Support](#support)

## How to contribute 🤝

To contribute to the project, please follow these steps:

1. **Check existing issues** and pull requests before starting work 🔍
2. **Create an issue** to discuss major changes before implementing 🗣️
3. **Implement updates** implement the changes you wish to contribute 💻
4. **Write tests** to verify your updates 🧪
5. **Ensure all tests pass** on the CI pipeline before marking the merge request as ready ✅
6. **Update documentation** as needed 📝
6. **Update version** Once updates have been made, update the version of the project accordingly
7. **Mark merge request as ready** with a clear description of your changes 🚦

## Contribution guidelines 📝

### Ticket guidelines 🏷️
- Use a clear and descriptive title 📝
- Reference related issues using `#issue-number` 🔗
- Use the issue template to describe the issue and the updates ✨

### Coding guidelines 💡
- Write clear, readable, and maintainable code.
- Follow the existing code style and conventions of the project.
- Use meaningful variable and function names.
- Add comments where necessary, especially for complex logic.
- Keep functions and components small and focused on a single responsibility.
- Remove unused code, variables, and imports.
- Avoid duplicating code; reuse existing utilities and components when possible.
- Write unit and integration tests for new features and bug fixes.
- Ensure your code passes linting and formatting checks.
- Document your code as necessary

### Commit Message Format 📝

Use conventional commit format:
```
type(scope): description

feat: add new feature
fix: resolve bug
chore: any change that is outside of the application itself such as local configuration, bundling or testing
```

### Versionning guidelines
The versionning of the project is done with the following format:
<MAJOR>.<MINOR>.<PATCH>
1. MAJOR version when you make incompatible changes with previous releases
2. MINOR version when you add functionality in a backward compatible manner
3. PATCH version when you make backward compatible bug fixes


## Testing 🧪
Before submitting your contribution, please ensure that you have thoroughly tested your changes. This includes:

- Writing unit tests for any new features or bug fixes.
- Running the full test suite locally to verify that all tests pass. (check the readme.md's testing section)
- Testing your changes in an environment that closely matches production, if possible.
- Checking for edge cases and potential regressions.
- Including tests for both expected and unexpected inputs.

If your contribution cannot be easily tested (e.g., documentation updates), please explain why in your merge request description.

We use automated CI pipelines to run tests on all merge requests. Your code must pass all tests before it can be merged.

## Deployment 🚀

Once the merge request has been accepted and merged into development, your changes will be present in the next production release by the DESP-AAS team.

## License 📝

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 📄

## Support 💬

- **Documentation** 📚: Check the `/docs` directory for detailed documentation
- **Issues** 🐞: Report bugs and feature requests on [Gitlab Issues](https://gitlab.acri-cwa.fr/desp-aas/sandbox_service/vm_management/-/issues)
- **Merge requests** 🔀: All ongoing merge requests [Gitlab Merge requests](https://gitlab.acri-cwa.fr/desp-aas/sandbox_service/vm_management/-/merge_requests)
- **Contact** ✉️: Reach out to the maintainers at [srv_dsy@acri-st.fr](mailto:srv_dsy@acri-st.fr)

---

**Note**: Replace placeholder URLs and email addresses with your actual project information.
