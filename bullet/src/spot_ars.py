#!/usr/bin/env python

import numpy as np
import matplotlib.pyplot as plt

from spotmicro.spot_gym_env import spotGymEnv
from spotmicro.util.gui import GUI
from spotmicro.Kinematics.SpotKinematics import SpotModel
from spotmicro.Kinematics.LieAlgebra import RPY
import time
from ars_lib.ars import ARSAgent, Normalizer, Policy, ParallelWorker
# Multiprocessing package for python
# Parallelization improvements based on:
# https://github.com/bulletphysics/bullet3/blob/master/examples/pybullet/gym/pybullet_envs/ARS/ars.py
import multiprocessing as mp
from multiprocessing import Pipe

import torch
import os

# Messages for Pipe
_RESET = 1
_CLOSE = 2
_EXPLORE = 3


def main():
    """ The main() function. """
    # Hold mp pipes
    mp.freeze_support()

    print("STARTING SPOT TEST ENV")
    seed = 0
    max_timesteps = 4e6
    eval_freq = 1e1
    save_model = True
    file_name = "spot_ars_"

    # Find abs path to this file
    my_path = os.path.abspath(os.path.dirname(__file__))
    results_path = os.path.join(my_path, "../results")
    models_path = os.path.join(my_path, "../models")

    if not os.path.exists(results_path):
        os.makedirs(results_path)

    if not os.path.exists(models_path):
        os.makedirs(models_path)

    env = spotGymEnv(render=False, on_rack=False)

    # Set seeds
    env.seed(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)

    state_dim = env.observation_space.shape[0]
    print("STATE DIM: {}".format(state_dim))
    action_dim = env.action_space.shape[0]
    print("ACTION DIM: {}".format(action_dim))
    max_action = float(env.action_space.high[0])

    env.reset()

    g_u_i = GUI(env.spot.quadruped)

    spot = SpotModel()
    T_bf = spot.WorldToFoot

    # Initialize Normalizer
    normalizer = Normalizer(state_dim)

    # Initialize Policy
    policy = Policy(state_dim, action_dim)

    # Initialize Agent with normalizer, policy and gym env
    agent = ARSAgent(normalizer, policy, env)
    agent_num = 0
    if os.path.exists(models_path + "/" + file_name + str(agent_num) +
                      "_policy"):
        print("Loading Existing agent")
        agent.load(models_path + "/" + file_name + str(agent_num))

    env.reset(agent.desired_velocity, agent.desired_rate)

    episode_reward = 0
    episode_timesteps = 0
    episode_num = 0

    # Create mp pipes
    num_processes = policy.num_deltas
    processes = []
    childPipes = []
    parentPipes = []

    # Store mp pipes
    for pr in range(num_processes):
        parentPipe, childPipe = Pipe()
        parentPipes.append(parentPipe)
        childPipes.append(childPipe)

    # Start multiprocessing
    # Start multiprocessing
    for proc_num in range(num_processes):
        p = mp.Process(target=ParallelWorker,
                       args=(childPipes[proc_num], env, state_dim))
        p.start()
        processes.append(p)

    print("STARTED SPOT TEST ENV")
    t = 0
    while t < (int(max_timesteps)):

        # Maximum timesteps per rollout
        t += policy.episode_steps

        episode_timesteps += 1

        episode_reward = agent.train_parallel(parentPipes)
        # episode_reward = agent.train()
        # +1 to account for 0 indexing.
        # +0 on ep_timesteps since it will increment +1 even if done=True
        print("="*1000)
        print("Total T: {} Episode Num: {} Episode T: {} Reward: {}, >400: {}".
              format(t, episode_num, policy.episode_steps, episode_reward,
                     agent.successes))
        # Reset environment
        episode_reward = 0
        episode_timesteps = 0

        # Evaluate episode
        if (episode_num + 1) % eval_freq == 0:
            if save_model:
                agent.save(models_path + "/" + str(file_name) +
                           str(episode_num))
                # replay_buffer.save(t)

        episode_num += 1

    # Close pipes and hence envs
    for parentPipe in parentPipes:
        parentPipe.send([_CLOSE, "pay2"])

    for p in processes:
        p.join()


if __name__ == '__main__':
    main()
