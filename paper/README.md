# CTK Technical Report

This directory contains the LaTeX source for the CTK technical report.

## Building the PDF

### Prerequisites

You need a LaTeX distribution installed:

**Ubuntu/Debian:**
```bash
sudo apt-get install texlive-latex-base texlive-latex-extra texlive-fonts-recommended
```

**macOS (with Homebrew):**
```bash
brew install --cask mactex
```

**Arch Linux:**
```bash
sudo pacman -S texlive-most
```

### Build Commands

```bash
# Build PDF (default)
make

# Build with bibliography
make bib

# Quick single-pass build
make quick

# View PDF
make view

# Clean auxiliary files
make clean

# Clean everything including PDF
make distclean
```

### Manual Build

If you prefer to build manually:

```bash
pdflatex ctk_technical_report.tex
pdflatex ctk_technical_report.tex  # Run twice for references
```

## Document Structure

- **Abstract**: Overview and contributions
- **Section 1**: Introduction and motivation
- **Section 2**: Related work
- **Section 3**: Architecture and data models
- **Section 4**: Implementation details
- **Section 5**: Evaluation and performance
- **Section 6**: Discussion and lessons learned
- **Section 7**: Conclusion
- **Appendices**: Installation guide and plugin development

## Editing

The document uses standard LaTeX packages:
- `hyperref` for links
- `listings` for code
- `algorithm`/`algpseudocode` for algorithms
- `booktabs` for tables
- `graphicx` for figures (if added)

## Figures

To add figures:
1. Place images in `paper/figures/` (create directory if needed)
2. Reference in LaTeX:
```latex
\begin{figure}[h]
\centering
\includegraphics[width=0.8\textwidth]{figures/architecture.png}
\caption{System Architecture}
\label{fig:architecture}
\end{figure}
```

## Citations

Update the bibliography section in the `.tex` file to add new references.

## Output

The compiled PDF will be: `ctk_technical_report.pdf`
