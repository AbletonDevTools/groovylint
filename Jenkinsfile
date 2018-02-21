@SuppressWarnings('VariableTypeRequired') // For _ variable
@Library(['ableton-utils@0.6.4', 'python-utils@0.3.0']) _

// Jenkins has some problems loading libraries from git references when they are
// named 'origin/branch_name' or 'refs/heads/branch_name'. Until this behavior
// is working, we need to strip those prefixes from the incoming HEAD_REF.
final String BRANCH = "${env.HEAD_REF}".replace('origin/', '').replace('refs/heads/', '')
library "groovylint@${BRANCH}"

import com.ableton.VirtualEnv as VirtualEnv


runTheBuilds.runDevToolsProject(
  setup: { data ->
    VirtualEnv venv = virtualenv.create(this, 'python3.6')
    venv.run('pip install flake8 pydocstyle pylint')
    data['venv'] = venv
  },
  build: { data ->
    data['image'] = docker.build('abletonag/groovylint')
  },
  test: { data ->
    parallel(failFast: false,
      flake8: {
        data['venv'].run('flake8 --max-line-length=90 -v *.py')
      },
      groovylint: {
        // Use the Docker image created in the Build stage above. This ensures that the
        // we are checking our own Groovy code with the same library and image which would
        // be published to production.
        groovylint.check('./Jenkinsfile,**/*.groovy', data['image'])
      },
      pydocstyle: {
        data['venv'].run('pydocstyle -v *.py')
      },
      pylint: {
        data['venv'].run('pylint --max-line-length=90 *.py')
      },
    )
  },
  deploy: { data ->
    runTheBuilds.runForSpecificBranches(['master'], false) {
      String version = readFile('VERSION').trim()
      docker.withRegistry('https://registry.hub.docker.com', 'docker-hub-password') {
        try {
          // Try to pull the image tagged with the contents of the VERSION file. If that
          // call fails, then we should push this image to the registry.
          docker.image(data['image'].id + ':' + version).pull()
        } catch (ignored) {
          data['image'].push(version)
          data['image'].push('latest')
        }
      }
    }
  },
)
