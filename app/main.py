# --- External imports
import asyncio
from asgi_lifespan import Lifespan, LifespanMiddleware
import json
import time
import threading
import numpy as np
# GraphQL
from ariadne import ObjectType, QueryType, MutationType, gql, make_executable_schema
from ariadne.asgi import GraphQL
from graphqlclient import GraphQLClient
# StarCraft II
import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer


class WorkerRushBot(sc2.BotAI):
    async def on_step(self, iteration):
        if iteration == 0:
            for worker in self.workers:
                await self.do(worker.attack(self.enemy_start_locations[0]))


# --- Constants

ACTION = "action"
AGENT_URI = "agentUri"
CLIENT = "client"
CODE = "code"
CONFIG = "config"
CONTEXT = "context"
DATA = "data"
ENDED = "Ended"
EPISODE = "episode"
ERROR = "Error"
ERRORS = "errors"
GAME_LOOP = "gameLoop"
ID = "id"
IDLE = "Idle"
MAP = "map"
MESSAGE = "message"
MODE = "mode"
OBSERVATION = "observation"
PERFORMING = "Performing"
REWARD = "reward"
RUNNING = "Running"
SIM_STATUS = "simStatus"
STARTING = "Starting"
STATUS = "status"
STEP = "step"
STOPPED = "Stopped"
THREAD = "thread"
TOKEN = "token"
TRAINING = "Training"

# --- Simulation


def set_sim_status(code, errors=[]):
    ts = time.time()
    app.state[STATUS] = {
        ID: "sc2@" + str(ts),
        CODE: code,
        ERRORS: errors}
    return app.state[STATUS]


def create_state():
    state = {
        CLIENT: None,
        CONFIG: None,
        THREAD: None,
        MAP: None,
        EPISODE: 0,
        STEP: 0,
        GAME_LOOP: 0,
        OBSERVATION: (0,),
        REWARD: 0,
        STATUS: None
    }
    app.state = state
    set_sim_status(IDLE)
    return state


def execute_client_request(graphql, variables=None):
    try:
        client = app.state[CLIENT]
        if (client == None):
            raise Exception("No client.  Running?")
        result = client.execute(graphql, variables)
        # print("result: " + result)
        json_result = json.loads(result)
        if (ERRORS in json_result):
            errors = json_result[ERRORS]
            if (errors != None):
                error_messages = [e[MESSAGE] for e in errors]
                set_sim_status(ERROR, error_messages)
                return None
        return json_result[DATA]
    except Exception as e:
        print("exception: " + repr(e))
        set_sim_status(ERROR, [str(e)])
        return None


def agent_on_reset():
    result = execute_client_request('''
    {
        onReset
    }
    ''')
    if (result == None):
        return None
    return result["onReset"]


def agent_on_step(state, last_reward, last_action, done, context):
    result = execute_client_request('''
        mutation onStep($state: [Float!]!, $lastReward: Float!, $lastAction: Int!, $isDone: Boolean!, $context: String) {
            onStep(state: $state, lastReward: $lastReward, lastAction: $lastAction, isDone: $isDone, context: $context) {
                id
                action
                context
            }
        }
    ''', {
        "state": state, "lastReward": last_reward, "lastAction": last_action, "isDone": done, "context": context
    })
    if (result == None):
        return None
    return result["onStep"]


def run_simulation(config):
    set_sim_status(STARTING)

    # env = try_make_env(config[MAP])
    # if (env == None):
    #     set_sim_status(
    #         ERROR, ["Can't load map: " + config[MAP]])
    #     return app.state[STATUS]
    # app.state[MAP] = env

    # client = GraphQLClient(config[AGENT_URI])
    # client.inject_token("Bearer " + config[TOKEN])
    # app.state[CLIENT] = client

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=run_episodes, args=(99, loop,))
    print("thread: " + repr(thread))
    app.state[THREAD] = thread
    thread.start()

    print("\n\n\nrun " + repr(config) + "\n\n\n\n\n")

    # set_sim_status(RUNNING)

    return app.state[STATUS]


def stop_simulation():
    set_sim_status(STOPPED)

    # Close the env and write monitor result info to disk
    env = app.state[MAP]
    if (env != None):
        env.close()

    thread = app.state[THREAD]
    if (thread != None):
        thread.join()

    return app.state[STATUS]


# --- OpenAI Gym

def try_make_env(mapId):
    try:
        return gym.make(mapId)
    except:
        return retro.make(mapId)
    return None


def run_episodes(episode_count, loop):
    try:
        print("run_episodes:" + str(episode_count))
        app.state[EPISODE] = 0
        app.state[REWARD] = 0

        set_sim_status(RUNNING)

        map = app.state[MAP]

        print("run_game starting...")

        asyncio.set_event_loop(loop)

        run_game(maps.get(map), [
            Bot(Race.Zerg, WorkerRushBot()),
            Computer(Race.Protoss, Difficulty.Medium)
        ], realtime=False)

        print("run_game finished!")

        # for i in range(episode_count):
        #     if (app.state[STATUS][CODE] != RUNNING):
        #         break

        #     app.state[EPISODE] = i

        #     done = False
        #     last_reward = 0
        #     last_action = 0

        #     ob = env.reset()
        #     print("episode #" + str(i) + ": " + repr(ob))

        #     agent_context = agent_on_reset()

        #     step = 0
        #     while app.state[STATUS][CODE] == RUNNING:
        #         app.state[STEP] = step
        #         step += 1

        #         state = ob
        #         if (isinstance(ob, np.ndarray)):
        #             state = ob.tolist()
        #         elif (isinstance(ob, np.int64) or isinstance(ob, int)):
        #             state = (float(ob),)
        #         else:
        #             print("type of state`: " + repr(type(state)))

        #         app.state[OBSERVATION] = state

        #         on_step_result = agent_on_step(
        #             state, last_reward, last_action, done, agent_context)

        #         # print("on_step_result " + repr(on_step_result))

        #         if (app.state[STATUS][CODE] == ERROR):
        #             break

        #         # last_action = env.action_space.sample()
        #         last_action = on_step_result[ACTION]
        #         agent_context = on_step_result[CONTEXT]

        #         ob, last_reward, done, _ = env.step(last_action)
        #         app.state[REWARD] += last_reward

        #         if done:
        #             agent_on_step(ob, last_reward, last_action,
        #                           done, agent_context)
        #             print("- DONE!")
        #             break

        #         print("- step = " + str(step) + ", reward = " +
        #               str(last_reward) + ", ob = " + repr(ob))

        #         # Note there's no env.render() here. But the map still can open window and
        #         # render if asked by env.monitor: it calls env.render('rgb_array') to record video.
        #         # Video is not recorded every episode, see capped_cubic_video_schedule for details.

        #         # render = env.render('rgb_array')
        #         # print("- render " + repr(render))

        # status = app.state[STATUS]
        # if (status[CODE] != ERROR and status[CODE] != STOPPED):
        #     set_sim_status(ENDED)

    except Exception as e:
        print("exception: " + repr(e))
        set_sim_status(ERROR, [str(e)])

    # finally:
        # Close the env and write monitor result info to disk
        # env.close()

# --- GraphQL


# Map resolver functions to Query and Mutation fields
query = QueryType()
mutation = MutationType()

# Define types using Schema Definition Language (https://graphql.org/learn/schema/)
# Wrapping string in gql function provides validation and better error traceback
type_defs = gql("""

    enum StatusCode {
        Idle
        Starting
        Running
        Stopped
        Ended
        Error
    }

    enum Mode {
        Training
        Performing
    }

    type SimStatus {
        id: ID!
        gameLoop: Int!
        code: StatusCode!
        mode: Mode!
        errors: [String!]!
    }

    input PlayerInput {
        race: Int!
        uri: String
        token: String
    }

    input ConfigInput {
        map: ID!
        mode: Mode!
        players:[PlayerInput!]!
    }

    type Map {
        id: ID!
    }

    type Observation {
        episode: Int!
        step: Int!
        data: [Float!]!
        reward: Float!
        simStatus: SimStatus!
    }

    type Query {
        listMaps: [Map!]!
        simStatus: SimStatus!
        observe: Observation!
        test: String!
    }
    type Mutation {
        run(config: ConfigInput!): SimStatus!
        stop: SimStatus!
    }
""")


# Resolvers are simple python functions

@query.field("listMaps")
def resolve_listMaps(*_):
    return [{"id": x.name} for x in maps.get()]


@query.field("simStatus")
def resolve_simStatus(*_):
    return app.state[STATUS]


@query.field("observe")
def resolve_observe(*_):
    observation = {
        EPISODE: app.state[EPISODE],
        STEP: app.state[STEP],
        REWARD: app.state[REWARD],
        DATA: app.state[OBSERVATION],
        SIM_STATUS: app.state[STATUS]
    }
    print('observe: ' + repr(observation))
    return observation


@mutation.field("stop")
def resolve_stop(*_):
    return stop_simulation()


@mutation.field("run")
def resolve_run(*_, config):
    return run_simulation(config)


# Create executable GraphQL schema
schema = make_executable_schema(type_defs, [query, mutation])

# --- ASGI app

# 'Lifespan' is a standalone ASGI app.
# It implements the lifespan protocol,
# and allows registering lifespan event handlers.
lifespan = Lifespan()


@lifespan.on_event("startup")
async def startup():
    print("Starting up...")
    print("... done!")


@lifespan.on_event("shutdown")
async def shutdown():
    print("Shutting down...")
    stop_simulation()
    print("... done!")

# Create an ASGI app using the schema, running in debug mode
app = GraphQL(schema, debug=True)

# 'LifespanMiddleware' returns an ASGI app.
# It forwards lifespan requests to 'lifespan',
# and anything else goes to 'app'.
app = LifespanMiddleware(app, lifespan=lifespan)

# Create shared state on the app object
create_state()
