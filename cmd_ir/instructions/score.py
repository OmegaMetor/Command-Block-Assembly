"""Variable Arithmetic Instructions"""

from ._core import Insn, READ, WRITE, get_subclasses
from ..variables import Variable, VarType, CompilerVariable

import commands as c

class SetScore(Insn):

    args = [Variable, (int, Variable, float)]
    access = [WRITE, READ]
    argnames = 'var value'
    argdocs = ["Variable to set the value on", "Value to set"]
    insn_name = '#invalid_setscore'

    def validate(self):
        if isinstance(self.value, Variable):
            # Allow nbt=nbt
            assert self.var.type.isnumeric or \
                   self.var.type == self.value.type == VarType.nbt, "%s, %s" % (
                       self.var.type, self.value.type)
        else:
            assert self.var.type.isnumeric

    def declare(self):
        self.var.usage_write()
        if isinstance(self.value, Variable):
            self.value.usage_read()

    def apply(self, out, func):
        if isinstance(self.value, Variable):
            self.value.clone_to(self.var, out)
        else:
            self.var.set_const_val(self.value, out)

    def run(self):
        assert isinstance(self.var, CompilerVariable)
        if isinstance(self.value, Variable):
            assert isinstance(self.value, CompilerVariable), self
            value = self.value.get_value()
        else:
            value = self.value
        self.var.set_value(value)

    def serialize(self, holder):
        return '%s = %s' % tuple(self.serialize_args(holder))

class SimpleOperationInsn(Insn):

    args = [Variable, (int, Variable, float)]
    access = [WRITE, READ]
    argnames = 'dest src'
    argdocs = ["Destination for the operation", "Source for the operation"]
    insn_name = '#invalid_operation'
    with_neg_const = None
    is_additive = False

    def validate(self):
        assert self.dest.type.isnumeric
        if isinstance(self.src, Variable):
            assert self.src.type.isnumeric

    def declare(self):
        # Maybe a read is needed here. Don't for now to allow dead elimination
        # self.dest.usage_read()
        self.dest.usage_write()
        if isinstance(self.src, Variable):
            self.src.usage_read()

    def apply(self, out, func):
        # Possible optimisation where scope exit ("put back" value) is applied
        # directly to operation i.e. store result ... scoreboard add ...
        with self.dest.open_for_write(out, read=True) as ref:
            if isinstance(self.src, Variable):
                with self.src.open_for_read(out) as srcref:
                    scaled, is_temp = self.dest.scale_other_to_this(self.src,
                                                                    srcref, out)
                    out.write(self.with_ref(ref, scaled))
                    if is_temp:
                        out.free_temp(scaled)
            else:
                self.apply_const_src(ref, self.dest.to_int(self.src), out)
            if not self.is_additive:
                self.dest.scale_down(ref, out)

    def apply_const_src(self, ref, val, out):
        if val < 0 and self.with_neg_const is not None:
            out.write(self.with_neg_const(ref, -val))
        else:
            out.write(self.with_const(ref, val))

    def run(self):
        assert isinstance(self.dest, CompilerVariable)
        if isinstance(self.src, Variable):
            assert isinstance(self.src, CompilerVariable)
            src = self.src.get_value()
        else:
            src = self.src
        self.dest.set_value(self.constfunc(self.dest.get_value(), src))

    def serialize(self, holder):
        dest, src = self.serialize_args(holder)
        return '%s %s %s' % (dest, self.with_ref.op, src)

    __op_lookup = {}

    @classmethod
    def lookup_by_op(cls, op):
        if not len(cls.__op_lookup):
            for clz in get_subclasses(cls):
                if hasattr(clz, 'with_ref'):
                    cls.__op_lookup[clz.with_ref.op] = clz
        return cls.__op_lookup[op]

import operator

class OnlyRefOperationInsn(SimpleOperationInsn):

    def apply_const_src(self, ref, val, out):
        srcref = out.allocate_temp()
        out.write(c.SetConst(srcref, val))
        out.write(self.with_ref(ref, srcref))
        out.free_temp(srcref)

class AddScore(SimpleOperationInsn):
    with_ref = c.OpAdd
    with_const = c.AddConst
    with_neg_const = c.RemConst
    constfunc = operator.add
    identity = 0
    is_additive = True

class SubScore(SimpleOperationInsn):
    with_ref = c.OpSub
    with_const = c.RemConst
    with_neg_const = c.AddConst
    constfunc = operator.sub
    identity = 0
    is_additive = True

class MulScore(OnlyRefOperationInsn):
    with_ref = c.OpMul
    constfunc = operator.mul
    identity = 1

class DivScore(OnlyRefOperationInsn):
    with_ref = c.OpDiv
    constfunc = operator.floordiv
    identity = 1

class ModScore(OnlyRefOperationInsn):
    with_ref = c.OpMod
    constfunc = operator.mod
    identity = None
    is_additive = True

class MovLtScore(OnlyRefOperationInsn):
    with_ref = c.OpIfLt
    constfunc = lambda a, b: b if b < a else a
    identity = None

class MovGtScore(OnlyRefOperationInsn):
    with_ref = c.OpIfGt
    constfunc = lambda a, b: b if b > a else a
    identity = None

class SwapScore(OnlyRefOperationInsn):
    args = [Variable, Variable]
    access = [WRITE, WRITE]
    with_ref = c.OpSwap
    constfunc = None
    identity = None
