#!/bin/bash

# Setup git hooks for the repository
# This script copies the pre-commit hook to .git/hooks and makes it executable

echo "Setting up git hooks..."

# Create .git/hooks directory if it doesn't exist
mkdir -p .git/hooks

# Copy pre-commit hook
cp scripts/pre-commit .git/hooks/pre-commit

# Make it executable
chmod +x .git/hooks/pre-commit

echo "✅ Git hooks setup complete!"
echo "The pre-commit hook will now run ruff check and format validation before each commit."
