# Changelog

All notable changes to DeepFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-05-18

### Added
- Frontend UI with FastAPI + React + Material Design (Phase 1-7)
- Task queue with file-based persistence and SQLite
- Webhook integration for OpenClaw Gateway
- Cron job processor for automated task handling
- Feishu document export functionality
- Contract Cage integration for spec validation
- Solution Pro V3.1 with 8 agent harnesses
- Configuration-driven architecture
- API documentation and architecture flow diagrams

### Changed
- Updated .gitignore to exclude sensitive configs and generated files
- Improved session naming with short prefixes

## [0.1.0] - 2026-05-06

### Added
- Multi-agent pipeline framework (10 stages)
- EntryHarness for startup validation
- PipelineOrchestrator for worker scheduling
- Quality gates with Harness V2 scoring
- DataManager Worker for unified data collection
- Contract Cage validation framework
- Investment Analysis domain (vertical scenario)
- Solution Pro domain (core framework)
- Prompt Registry for extensibility
- Comprehensive documentation (ARCHITECTURE.md, etc.)

### Notes
- Platform dependency: OpenClaw required for core scheduling
- Three-layer architecture: Platform → Framework → Domain
