import json
import pwd
import grp
import os
import shutil
import glob
from tornado import gen

from jupyterhub.spawner import LocalProcessSpawner

KERNEL_TEMPLATE = """{
 "argv": ["%s", "-m", "IPython.kernel", 
          "-f", "{connection_file}"],
 "display_name": "%s",
 "language": "python",
 "env": {"PATH": "%s"}
}
"""

def rchown(path, user, group):
    uid = pwd.getpwnam(user).pw_uid
    guid = grp.getgrnam(group).gr_gid
    os.chown(path, uid, guid)
    for root, dirs, files in os.walk(path):
        for momo in dirs:
            os.chown(os.path.join(root, momo), uid, guid)
        for momo in files:
            os.chown(os.path.join(root, momo), uid, guid)

class CondaSpawner(LocalProcessSpawner):
    
    def get_state(self):
        state = super(CondaSpawner, self).get_state()
        if self.kernel_paths:
            state['kernel_paths'] = self.kernel_paths
        if self.profile_paths:
            state['profile_paths'] = self.profile_paths
        return state

    def load_state(self, state):
        super(CondaSpawner, self).load_state(state)
        if 'kernel_paths' in state:
            self.kernel_paths = state['kernel_paths']
        if 'profile_paths' in state:
            self.profile_paths = state['profile_paths']

    def clear_state(self):
        super(CondaSpawner, self).clear_state()
        self.kernel_paths = []
        self.profile_paths = []

    def _find_conda_envs(self):
        env_path = '/home/{0}/.conda/envs'.format(self.user.name)
        envs = [os.path.join(env_path, i) for i in os.listdir(env_path)
                if not i.startswith('.')]
        envs = [(os.path.split(i)[1] + "-conda", os.path.join(i, 'bin/python'))
                for i in envs if glob.glob('{0}/conda-meta/ipython-notebook-*'.format(i))]
        return envs 

    def _create_kernels(self, envs):
        kernel_paths = []
        for env, python in envs:
            kernel_path = '/home/{0}/.ipython/kernels/AUTO_{1}'.format(self.user.name,
                                                                             env)
            path_var = os.path.dirname(python) + ":" + os.environ['PATH']
            kernel_paths.append(kernel_path)
            kernel_json = os.path.join(kernel_path, 'kernel.json')
            os.makedirs(kernel_path, exist_ok=True)
            with open(kernel_json, mode='w') as f:
                f.write(KERNEL_TEMPLATE % (python, env, path_var))
        self.kernel_paths = kernel_paths

    def _create_profiles(self, envs):
        profile_paths = []
        for env, python in envs:
            profile_path = '/home/{0}/.ipython/profile_{1}'.format(self.user.name, 
                                                                         env)
            profile_paths.append(profile_path)
            os.system(("ipython profile create --parallel"
                       " --profile-dir {0}").format(profile_path))
            with open(os.path.join(profile_path, "ipcluster_config.py"), mode='a') as f:
                f.write("\n")
                f.write(("c.LocalEngineLauncher.engine_cmd = ['{0}', '-m',"
                         " 'IPython.parallel.engine']").format(python))
        self.profile_paths = profile_paths       

    @gen.coroutine
    def start(self):
        envs = self._find_conda_envs()
        self._create_kernels(envs)
        self._create_profiles(envs)
        ipydir = '/home/{0}/.ipython'.format(self.user.name)
        rchown(ipydir, self.user.name, self.user.name)
        return super(CondaSpawner, self).start()

    @gen.coroutine
    def stop(self, now=False):
        for k_path in self.kernel_paths:
            shutil.rmtree(k_path)
        for p_path in self.profile_paths:
            shutil.rmtree(p_path)

        return super(CondaSpawner, self).stop(now=now)


	
