# GitHub upload steps

Git is not currently available in this PowerShell session, so the repository cannot be initialized from here until Git is installed or added to the PATH.

## Option A: GitHub Desktop

1. Open GitHub Desktop.
2. Choose **File > Add local repository**.
3. Select:

   ```text
   C:\Users\ladel\OneDrive\Documentos\Plugin\extracted\bestfitinterpolator
   ```

4. If GitHub Desktop says it is not a repository, choose **create a repository** from that folder.
5. Repository name:

   ```text
   BestFitInterpolation
   ```

6. Commit all files with a message such as:

   ```text
   Prepare BestFitInterpolator QGIS plugin release
   ```

7. Publish the repository to GitHub.

## Option B: Command line after installing Git

Run these commands from:

```text
C:\Users\ladel\OneDrive\Documentos\Plugin\extracted\bestfitinterpolator
```

```powershell
git init
git branch -M main
git add .
git commit -m "Prepare BestFitInterpolator QGIS plugin release"
git remote add origin https://github.com/ladelgadobe/BestFitInterpolation.git
git push -u origin main
```

If the remote repository already exists and has files, run:

```powershell
git pull origin main --allow-unrelated-histories
git push -u origin main
```

## Release ZIP

For a GitHub Release, attach the ZIP file generated from the parent folder so it contains the top-level `bestfitinterpolator` directory.

