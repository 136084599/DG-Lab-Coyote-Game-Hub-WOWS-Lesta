# -*- coding: utf-8 -*-
"""Lesta ModsAPI recorder; install explicitly with tools/install_mod.py.

Uses the same game API fields as the original recorder. Validate against the
installed game version before depending on its event data.
"""
import datetime
import time
# utils/events/battle/callbacks are injected by ModsAPI, not importable packages.

API_VERSION = 'API_v1.0'
MOD_NAME = 'BattleRecorder'
MOD_PATH = utils.getModDir()
LOG_PATH = MOD_PATH.rstrip('/\\') + '/damage_log.txt'
DELAY = 0.2


class BattleRecorder(object):
    def __init__(self):
        self.timer = None
        self.running = False
        self.player_id = None
        self.achievements = 0
        self.last_payload = None
        self.unsupported = set()
        self.last_write = 0
        self.last_error = None

    def write(self, value, mode='a'):
        with open(LOG_PATH, mode) as stream:
            stream.write(value + '\n')

    def init(self, *args, **kwargs):
        self.destructor()
        self.running = True
        self.achievements = 0
        self.last_payload = None
        try:
            self.player_id = battle.getSelfPlayerInfo()['id']
        except Exception:
            self.player_id = None
        self.write('BattleStart,' + datetime.datetime.now().isoformat(), 'w')
        self.update()
        # ModsAPI callback repeats by itself; never register inside update().
        self.timer = callbacks.callback(DELAY, self.update)

    def status(self, method, ship):
        try:
            return bool(getattr(battle, method)(ship))
        except Exception as exc:
            if method not in self.unsupported:
                utils.logInfo(MOD_NAME, method + ' unavailable: ' + str(exc))
                self.unsupported.add(method)
            return False

    def update(self):
        if not self.running:
            return
        try:
            info = battle.getSelfPlayerInfo()
            if self.player_id is None:
                self.player_id = info['id']
            maximum = info['maxHealth']
            hp = info['shipGameData']['health']
            ship = info['shipId']
            payload = (maximum, hp, hp <= 0, self.status('isVehicleBurning', ship),
                       self.status('isVehicleFlooding', ship), info['fragsCount'], self.achievements)
            if payload != self.last_payload or time.time() - self.last_write >= 2:
                stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                self.write('{}({}),{},isDied:{},Burning:{},Flooding:{},Kills:{},Achievements:{}'.format(stamp, *payload))
                self.last_payload = payload
                self.last_write = time.time()
            self.last_error = None
        except Exception as exc:
            if str(exc) != self.last_error:
                utils.logInfo(MOD_NAME, 'Recorder error: ' + str(exc))
                self.last_error = str(exc)

    def achievement(self, *args, **kwargs):
        if self.running and len(args) >= 2 and self.player_id is not None and args[1] == self.player_id:
            self.achievements += 1

    def destructor(self, *args, **kwargs):
        was_running = self.running
        self.running = False
        if self.timer is not None:
            callbacks.cancel(self.timer)
            self.timer = None
        if was_running:
            self.write('BattleEnd')


recorder = BattleRecorder()
events.onBattleStart(recorder.init)
events.onBattleQuit(recorder.destructor)
events.onAchievementEarned(recorder.achievement)
recorder.write('RecorderLoaded,' + datetime.datetime.now().isoformat())
utils.logInfo(MOD_NAME, 'Recorder loaded; interval: ' + str(DELAY))
