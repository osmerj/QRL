# coding=utf-8
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.

from google.protobuf.json_format import MessageToJson, Parse

from qrl.core import config, logger
from qrl.core.StakeValidator import StakeValidator
from qrl.core.Transaction import StakeTransaction
from qrl.generated import qrl_pb2


class StakeValidatorsTracker:
    """
    Maintains the Stake validators list for current and next epoch
    """
    def __init__(self, stakevalidator_protobuf=None):
        self._data = stakevalidator_protobuf
        if not self._data:
            self._data = qrl_pb2.StakeValidatorsTracker()

    @property
    def sv_dict(self):
        return self._data.sv_dict

    @property
    def future_stake_addresses(self):
        return self._data.future_stake_addresses

    @property
    def expiry(self):
        return self._data.expiry

    @property
    def future_sv_dict(self):
        return self._data.future_sv_dict

    @property
    def total_stake_amount(self):
        return self._data.total_stake_amount

    @staticmethod
    def create():
        stake_validators_tracker = StakeValidatorsTracker()
        stake_validators_tracker._data.total_stake_amount = 0  # Maintains the total stake amount by current sv

        return stake_validators_tracker

    def add_sv(self, balance, stake_txn: StakeTransaction, blocknumber):
        logger.debug("Adding %d %s %s", blocknumber, stake_txn.txfrom, stake_txn)
        if stake_txn.activation_blocknumber > blocknumber:
            self._add_future_sv(balance, stake_txn)
        else:
            self._activate_sv(balance, stake_txn)

    def _activate_sv(self, balance, stake_txn):
        if stake_txn.txfrom in self.sv_dict:
            logger.info('Stake Validator already in Current Staker, sv_dict')
            return
        sv = StakeValidator.create(balance, stake_txn)
        self._data.sv_dict[stake_txn.txfrom].MergeFrom(sv.pbdata)
        self._data.total_stake_amount += sv.balance
        self._data.expiry[stake_txn.activation_blocknumber + config.dev.blocks_per_epoch].addresses.extend([stake_txn.txfrom])

    def _add_future_sv(self, balance, stake_txn):
        if stake_txn.txfrom in self._data.future_stake_addresses:
            logger.info('Stake Validator already in Future Staker, future_sv_dict')
            return
        sv = StakeValidator.create(balance, stake_txn)

        self._data.future_stake_addresses[stake_txn.txfrom].MergeFrom(sv.pbdata)
        self._data.future_sv_dict[stake_txn.activation_blocknumber].stake_validators.extend([sv.pbdata])

    def _activate_future_sv(self, sv):
        self._data.sv_dict[sv.address].MergeFrom(sv)
        self._data.total_stake_amount += sv.balance
        self._data.expiry[sv.activation_blocknumber + config.dev.blocks_per_epoch].addresses.extend([sv.address])

    def update_sv(self, blocknumber):
        next_blocknumber = blocknumber + 1
        if next_blocknumber in self._data.expiry:
            for sv_addr in self._data.expiry[next_blocknumber].addresses:
                self._data.total_stake_amount -= self._data.sv_dict[sv_addr].balance
                del self._data.sv_dict[sv_addr]
            del self._data.expiry[next_blocknumber]

        if next_blocknumber in self._data.future_sv_dict:
            sv_set = self._data.future_sv_dict[next_blocknumber].stake_validators
            for sv in sv_set:
                self._activate_future_sv(sv)
                del self._data.future_stake_addresses[sv.address]
            del self._data.future_sv_dict[next_blocknumber]

    def validate_hash(self,
                      reveal_hash: bytes,
                      block_idx: int,
                      stake_address: bytes=None)->bool:

        if stake_address not in self._data.sv_dict:
            return False

        sv = StakeValidator(self._data.sv_dict[stake_address])
        result = sv.validate_hash(reveal_hash, block_idx)
        self._data.sv_dict[stake_address].CopyFrom(sv.pbdata)
        return result

    def get_stake_balance(self, stake_address: bytes)->int:
        if stake_address not in self._data.sv_dict:
            logger.warning('Stake address %s not found in Stake Validators Tracker', stake_address)
            raise Exception

        return self._data.sv_dict[stake_address].balance

    def get_total_stake_amount(self):
        return self.total_stake_amount

    def increase_nonce(self, address):
        self.sv_dict[address].nonce += 1

    @staticmethod
    def from_json(json_data):
        pbdata = qrl_pb2.StakeValidatorsTracker()
        Parse(json_data, pbdata)
        return StakeValidatorsTracker(pbdata)

    def to_json(self):
        return MessageToJson(self._data)
