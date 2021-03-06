% option data defaults
#const show=0.
#const accuracy=1.
#const epsilon=(1,3). % similar to cplex default
#const nstrict=1.
#const solver=lps.
#const trace=0.
#const core_confl=20.
#const prop_heur=0.
#const debug=0.
#const ilp=0.


#script (python)


import sys
import time

try:
    from cplx import cplx
except ModuleNotFoundError as e:
    print('cplex not found, using lp_solve')
from lps import lps


class Propagator:

    class State:

        def __init__(self):
            self.stack = []             # [(decision level, lp_trail index, cond_trail index, oclit_trail index)]
            self.lp_trail = []          # [lp literal]
            self.eq_trail = []          # [nlit]
            self.cond_trail = []        # [conditional literals]
            self.eqlit = {}             # {cnum : nlit}
            self.eqlit_inv = {}         # {nlit : cnum}
            self.clist = {}             # {cnum : ({varname : weights}, rel, brow)}
            self.active_cnum = {}       # {cnum : [clit_undec, truth_value, nlit_introduced]}
            self.recent_active = []     # [cnum]
            self.total_lits = 0
            self.oclit_trail = []       # [oclits]
            self.oclit_recent_active = 0
            self.active_oclit = 0       # number of undec oclits
            self.lits_current = 0       # number of decided watched literals
            self.lp = None              # lpsolve object  
            self.current_assignment = None
            self.stats = ''
            self.times = (0,0,0,0,0,0)  # (scalls, stime, addcalls, addtime, resetcalls, resettime)
            self.times_print = ''


        def save_assignment(self, accuracy):
            self.current_assignment = self.lp.get_solution(accuracy)


        def save_stats(self, solver, debug, initcalls, inittime, propcalls, proptime, undocalls, undotime, checkcalls, checktime):
            self.stats = self.lp.get_stats()
            if solver == 'lps':
                if self.lp.get_time() != 'Error' and self.lp.get_time() != 'Unsat':
                    times = self.lp.get_time()
                    self.times = (self.times[0] + times[0], self.times[1] + times[1], self.times[2] + times[2], self.times[3] + times[3], self.times[4] + times[4], self.times[5] + times[5])
                self.times_print = 'LP solver calls: ' + str(self.times[0]) + '   Time lp_solve :  ' + str(self.times[1]) + '\n'
            elif solver == 'cplx':
                if self.lp.get_time() != 'Error' and self.lp.get_time() != 'Unsat':
                    times = self.lp.get_time()
                    self.times = (self.times[0] + times[0], self.times[1] + times[1], self.times[2] + times[2], self.times[3] + times[3], self.times[4] + times[4], self.times[5] + times[5])
                self.times_print = 'LP solver calls: ' + str(self.times[0]) + '   Time cplex :  ' + str(self.times[1]) + '\n'
            if debug > 0:
                self.times_print = self.times_print + '\n' + 'Calls init: ' + str(initcalls) + '      Time init:  ' + str(inittime) + '\n' + 'Calls propagate: ' + str(propcalls) + '      Time propagate:  ' + str(proptime) + '\n' + 'Calls undo: ' + str(undocalls) + '      Time undo:  ' + str(undotime) + '\n' + 'Calls add: ' + str(self.times[2]) + '      Time add:  ' + str(self.times[3]) + '\n' + 'Calls reset: ' + str(self.times[4]) + '      Time reset:  ' + str(self.times[5]) + '\n' + 'Calls check: ' + str(checkcalls) + '      Time check:  ' + str(checktime)



        def print_assignment(self, show):
            print('')
            print('LP Solver output')
            if show:
                print(self.stats) 
                print('')
                print('solution')
                print(self.current_assignment)
                print('')
                print(self.times_print)
                print('')
            else:
                print(self.current_assignment)
                print('')
                print(self.times_print)
                print('')


    def __state(self, sid): 
        while len(self.__states) <= sid:
            self.__states.append(Propagator.State())
            state = self.__states[len(self.__states)-1]
            self.update_state_info(state)
        return self.__states[sid]


    def update_state_info(self, state):
        state.total_lits = self.__lits_total_num
        for cnum in self.__constr: 
            if not cnum in state.active_cnum:
                if not cnum in self.__constr_clit:
                    state.active_cnum[cnum] = [0,0,0]
                else:
                    state.active_cnum[cnum] = [len(self.__constr_clit[cnum]),0,0]
        state.active_oclit = len(self.__obj_cond_lit)
        try:
            lp_solver_class = globals()[self.__solver] 
            state.lp = lp_solver_class(self.__varpos, self.__bounds, self.__ilp)
        except:
            print('No wrapper class of ', self.__solver, ' found!')
            exit()



    def __init__(self, show, accuracy, nstrict, epsilon, solver, trace, core_confl, prop_heur, debug, ilp):      
        self.__var_ta = {}              # {abs(lit) : [cnum]}
        self.__lit_ta = {}              # {lit : [cnum]}
        self.__constr = {}              # {cnum : (lit,constr)}
        self.__clit_constr = {}         # {clit : [cnum]}
        self.__constr_clit = {}         # {cnum : [clits]}
        self.__states = []              # [state]
        self.__objective = {}           # {varname : [weight or {clit : weight}]}
        self.__obj_cond_lit = set()     # {objclit}
        self.__optim = ''               # min or max (depends on first input)
        self.__bounds = {}              # {varname : [(lower bound, upper bound)]}
        self.__varpos = {}              # {varname : var_pos}
        self.__vars = set()             # {vars} 
        self.__wopt = {}                # {varname : weight}
        self.__lits_total = set()       # set of all watched literals
        self.__lits_total_num = 0       # number of watched literals
        self.__time = 0.0               # get time of propagation
        self.__inittime = 0.0
        self.__initcalls = 0
        self.__proptime = 0.0
        self.__propcalls = 0
        self.__undotime = 0.0
        self.__undocalls = 0
        self.__checktime = 0.0
        self.__checkcalls = 0
        if 'None' == str(accuracy):
            self.__accuracy = 0
        else:
            self.__accuracy = accuracy.number
        if 'None' == str(show) or show.number != 1:
            self.__show = False
        else:
            self.__show = True
        if 'None' == str(nstrict) or nstrict.number != 1:
            self.__nstrict = False
        else:
            self.__nstrict = True
        if 'None' == str(epsilon): # epsilon=(a,b) -> a*10^-b
            self.__epsilon = 0.001 
        else:
            tmp = str(epsilon)[1:-1].split(",")
            koef = float(tmp[0])
            exp = float(tmp[1])
            self.__epsilon = koef*10**-exp
        if 'None' == str(trace) or trace.number != 1:
            self.__trace = False
        else:
            self.__trace = True
        if 'None' == str(core_confl):
            self.__core_confl_heur = 100
        else:
            self.__core_confl_heur = core_confl.number
        if 'None' == str(prop_heur):
            self.__prop_heur = 100
        else:
            self.__prop_heur = prop_heur.number
        self.__solver = solver.name
        if 'None' == str(debug):
            self.__debug = 0
        else:
            self.__debug = debug.number
        if 'None' == str(ilp) or ilp.number != 1:
            self.__ilp = False
        else:
            self.__ilp = True
            self.__epsilon = 1   


    def init(self, init):
        start = time.process_time()
        for atom in init.theory_atoms:
            term = atom.term
            if term.name == 'lp' or term.name == 'sum':
                self.__lp_structure(atom, init)
            if term.name == 'objective' or term.name == 'minimize' or term.name == 'maximize':
                self.__lp_objective(atom, init)
            if term.name == 'dom':
                self.__lp_domain(atom)
        if len(self.__obj_cond_lit) == 0:
            for varname in self.__objective:
                weight = sum(self.__objective[varname])
                if weight != 0:
                    self.__wopt[varname] = weight
        self.__lits_total_num = len(self.__lits_total)
        col_pos = 0
        for varname in self.__vars:
            col_pos = col_pos +1
            self.__varpos[varname] = col_pos
        end = time.process_time()
        self.__inittime += end-start
        self.__initcalls += 1
        self.__time = self.__time + end-start



    def print_assignment(self, thread_id):
        state = self.__state(thread_id)
        state.print_assignment(self.__show)


    # resolves structure of lp-statements and saves it
    def __lp_structure(self, atom, init): 
        lit=init.solver_literal(atom.literal)
        n = len(self.__constr)+1
        init.add_watch(lit)
        init.add_watch(-lit)
        var = abs(lit)
        self.__lits_total.add(var)
        weights = {}
        lhs = atom.elements
        rhs = atom.guard[1]
        rel = atom.guard[0]
        for elem in lhs:
            if str(elem.terms[0].type) == "Function" and str(elem.terms[0].name) == '*': 
                koef = self.__calc_bound(elem.terms[0].arguments[0])
                if elem.terms[0].arguments[1].arguments == []:
                    varname = elem.terms[0].arguments[1].name
                else:
                    varname = str(elem.terms[0].arguments[1])
            else:
                koef = 1
                if elem.terms[0].arguments == []:
                    varname = elem.terms[0].name
                else:
                    varname = str(elem.terms[0])
            self.__vars.add(varname)
            if elem.condition != []:
                clit = init.solver_literal(elem.condition_id) 
                init.add_watch(clit)
                init.add_watch(-clit)
                aclit = abs(clit)
                self.__lits_total.add(aclit)
                self.__clit_constr.setdefault(aclit,[])
                if not n in self.__clit_constr[aclit]:
                    self.__clit_constr[aclit].append(n)
                self.__constr_clit.setdefault(n,[])
                if not clit in self.__constr_clit[n]:
                    self.__constr_clit[n].append(aclit) 
                    self.__constr_clit[n] = list(set(self.__constr_clit[n]))
                tmp = {}
                if str(elem.terms[0].type) == "Function" and str(elem.terms[0].name) == '*':
                    tmp[clit] = self.__calc_bound(elem.terms[0].arguments[0])
                else: 
                    tmp[clit] = 1
                weights.setdefault(varname,[]).append(tmp)
            else:
                weights.setdefault(varname,[]).append(koef)
        self.__constr[n] = (lit, (dict(weights),rel,self.__calc_bound(rhs)))
        self.__var_ta.setdefault(var,[]).append(n)
        self.__lit_ta.setdefault(lit,[]).append(n)



    # resolves structure of objective-statements and saves it
    def __lp_objective(self, atom, init):
        obj = atom.elements
        mode = ''
        if atom.term.name == 'objective': ## at some point not longer part of syntax!
            mode = str(atom.term.arguments[0])
            if self.__optim == '':
                self.__optim = mode
        if atom.term.name == 'maximize':
            mode = 'max'
            if self.__optim == '':
                self.__optim = mode
        if atom.term.name == 'minimize':
            mode = 'min'
            if self.__optim == '':
                self.__optim = mode
        if mode == self.__optim:
            pol = 1
        else:
            pol = -1
        self.__set_objective(init,obj,pol)


    def __set_objective(self,init, obj,pol):
        for elem in obj:
            if str(elem.terms[0].type) == "Function" and str(elem.terms[0].name) == '*': 
                koef = self.__calc_bound(elem.terms[0].arguments[0]) 
                if elem.terms[0].arguments[1].arguments == []:
                    varname = elem.terms[0].arguments[1].name
                else:
                    varname = str(elem.terms[0].arguments[1])
            else:
                koef = 1
                if elem.terms[0].arguments == []:
                    varname = elem.terms[0].name
                else:
                    varname = str(elem.terms[0])
            self.__vars.add(varname)
            if elem.condition != []:
                clit = init.solver_literal(elem.condition_id)
                aclit = abs(clit)
                init.add_watch(clit)
                init.add_watch(-clit)
                self.__lits_total.add(aclit)
                self.__obj_cond_lit.add(aclit)
                tmp = {}
                if str(elem.terms[0].type) == "Function" and str(elem.terms[0].name) == '*':
                    tmp[clit] = self.__calc_bound(elem.terms[0].arguments[0])
                else: 
                    tmp[clit] = 1
                self.__objective.setdefault(varname,[]).append(tmp)
            else: 
                self.__objective.setdefault(varname,[]).append(pol*koef)



    # resolves structure of domain-statements and saves it
    def __lp_domain(self, atom):
        varname = str(atom.guard[1])
        if atom.elements != []:
            for dom in atom.elements:
                lb = self.__calc_bound(dom.terms[0].arguments[0])
                ub = self.__calc_bound(dom.terms[0].arguments[1])
                self.__bounds.setdefault(varname,[]).append((lb,ub))
        else:
            lb = 'none'
            ub = 'none'
            self.__bounds.setdefault(varname,[]).append((lb,ub))



    # calculates bounds of input expressions
    def __calc_bound(self, expr):
        args = expr.arguments
        tmp = 0
        if len(args) == 2:
            if expr.name == '+':
                tmp = self.__calc_bound(args[0])+self.__calc_bound(args[1])
            elif expr.name == '-':
                tmp = self.__calc_bound(args[0])-self.__calc_bound(args[1])
            elif expr.name == '*':
                tmp = self.__calc_bound(args[0])*self.__calc_bound(args[1])
            elif expr.name == '/':
                tmp = self.__calc_bound(args[0])/self.__calc_bound(args[1])
        elif len(args) == 1:
            if args[0].arguments == []:
                tmp = -self.__get_number(args[0])
            else:
                tmp = -self.__calc_bound(args[0])
        else:
            tmp = self.__get_number(expr)
        return tmp



    # cast gringo number or string to float
    def __get_number(self, num):
        if str(num)[0] != '"':
            return float(num.number)
        else:
            return float(str(num)[1:-1])



    # solve call
    def __solve(self, state):
        if state.lp.is_valid():
            state.clist.update(self.__get_constrs(state, state.recent_active))
            cnums = state.recent_active
        else:
            state.clist = dict(self.__get_constrs(state, [cnum for cnum in state.active_cnum if state.active_cnum[cnum][0] == 0 and state.active_cnum[cnum][1] != 0]))
            cnums = list(state.clist.keys())
        if state.active_oclit == 0:
            if self.__wopt == {}:
                obj = self.__set_obj(state)
            else:
                obj = self.__wopt
            state.oclit_recent_active = 0 
            state.lp.set_obj(obj, self.__optim)
        clist = []
        for cnum in cnums:
            clist.append(state.clist[cnum])
        state.lp.add_constr(clist)
        state.lp.solve_lp()
        state.save_assignment(self.__accuracy)
        state.save_stats(self.__solver, self.__debug, self.__initcalls, self.__inittime, self.__propcalls, self.__proptime, self.__undocalls, self.__undotime, self.__checkcalls, self.__checktime)



    # get constraints wrt current assignment
    def __get_constrs(self, state, cnums):
        clist = {}
        for cnum in cnums:
            clist[cnum] = (self.__get_constr(state,cnum))
        return clist
        


    # evaluates constr wrt current assignment
    def __get_constr(self, state, cnum): 
        constr = self.__constr[cnum][1] 
        trow = {}
        rel = constr[1]
        b = constr[2]
        for varname in constr[0]: 
            weight = self.__get_weight(state.cond_trail, constr[0][varname])
            if varname in self.__varpos: 
                trow[varname] = weight
        if state.active_cnum[cnum][1] < 0 and not self.__nstrict:
            if rel == '<':
                rel = '>='
            elif rel == '>':
                rel = '<='
            elif rel == '>=':
                rel = '<='
                b = b - self.__epsilon
            elif rel == '<=':
                rel = '>='
                b = b + self.__epsilon
            elif rel == '!=':
                rel = '='
            elif rel == '=':
                if state.eqlit[cnum] in state.eq_trail:
                    rel = '>='
                    b = b + self.__epsilon
                elif -state.eqlit[cnum] in state.eq_trail:
                    rel = '<='
                    b = b - self.__epsilon
        elif state.active_cnum[cnum][1] > 0:
            if rel == '<':
                rel = '<='
                b = b - self.__epsilon
            elif rel == '>':
                rel = '>='
                b = b + self.__epsilon
            elif rel == '!=':
                if state.eqlit[cnum] in state.eq_trail:
                    rel = '>='
                    b = b + self.__epsilon
                elif -state.eqlit[cnum] in state.eq_trail:
                    rel = '<='
                    b = b - self.__epsilon
        return (trow, rel, b)




    # sets objective dictionary {var: weight} wrt conditionals
    def __set_obj(self, state): 
        wopt = {} 
        for varname in self.__varpos:
            wopt.setdefault(varname,0)
        for varname in self.__objective:
            weight = self.__get_weight(state.oclit_trail, self.__objective[varname])
            wopt[varname] = weight
        return wopt



    # calculates weight of variable wrt a state
    def __get_weight(self, clits, w_list): 
        tmp = 0
        for weight in w_list:
            if not isinstance(weight, dict):
                tmp = tmp + weight
            else:
                for clit in weight:
                    if clit in clits:
                        tmp = tmp + weight[clit]
        return tmp
       


    def propagate(self, control, changes): 
        start = time.process_time()
        state = self.__state(control.thread_id)
        self.__update_state(control, changes, state)
        if (state.recent_active != [] or state.oclit_recent_active == 1) and state.lits_current*100 / self.__lits_total_num >= self.__prop_heur:
            self.__solve(state) 
            if self.__trace:
                print('')
                print('propagate with ', state.lits_current*100 / state.total_lits, '%', changes) 
                for constr in state.clist:
                    print(state.clist[constr])
                print('lp_trail: ', state.lp_trail)  
                print('cond_trail: ', state.cond_trail)
                print('eq_trail: ', state.eq_trail)
                print('')
            if state.lp.is_valid() and not self.__check_consistency(control, state):
                end = time.process_time()
                self.__proptime += end-start
                self.__propcalls += 1
                self.__time = self.__time + end-start
                return False
        end = time.process_time()
        self.__proptime += end-start
        self.__propcalls += 1
        self.__time = self.__time + end-start
        return True



    def undo(self, thread_id, assign, changes):
        start = time.process_time()
        state = self.__state(thread_id)
        lpid = state.stack[-1][1]
        cid = state.stack[-1][2]
        oid = state.stack[-1][3]
        nid = state.stack[-1][4]
        state.lits_current -= len(changes)
        for lit in state.lp_trail[lpid:]:
            var=abs(lit)
            for cnum in self.__var_ta[var]:
                state.active_cnum[cnum][1] = 0 
        for lit in state.cond_trail[cid:]:
            var=abs(lit)
            for cnum in self.__clit_constr[var]:
                state.active_cnum[cnum][0] += 1
        for lit in state.oclit_trail[oid:]:
            state.active_oclit += 1 
            state.oclit_recent_active = 0
        for lit in state.eq_trail[nid:]:
            var=abs(lit)
            cnum = state.eqlit_inv[var]
            state.active_cnum[cnum][0] += 1
        del state.lp_trail[lpid:]
        del state.cond_trail[cid:]
        del state.oclit_trail[oid:]
        del state.eq_trail[nid:]
        state.lp.reset()
        state.stack.pop()
        end = time.process_time()
        self.__undotime += end-start
        self.__undocalls += 1
        self.__time = self.__time + end-start



    def check(self, control):
        start = time.process_time()
        state = self.__state(control.thread_id)
        end = time.process_time()
        self.__checktime += end-start
        self.__checkcalls += 1
        self.__time = self.__time + end-start
        #times = state.lp.get_time()
        #print ''
        #if self.__debug > 0:
        #    print 'Calls init: ', self.__initcalls, '      Time init:  ', self.__inittime
        #    print 'Calls propagate: ', self.__propcalls, '      Time propagate:  ', self.__proptime
        #    print 'Calls undo: ', self.__undocalls, '      Time undo:  ', self.__undotime
        #    print 'Calls add: ', times[2], '      Time add:  ', times[3]
        #    print 'Calls reset: ', times[4], '      Time reset:  ', times[5]
        #    print 'Calls check: ', self.__checkcalls, '      Time check:  ', self.__checktime
        #if self.__solver == 'lps':
        #    print 'LP solver calls: ', times[0], '   Time lp_solve :  ', times[1]
        #elif self.__solver == 'cplx':
        #    print 'LP solver calls: ', times[0], '   Time cplex :  ', times[1]
        #print 'Time propagator:  ', self.__time
        #print ''
        return True


    # updates state wrt to changes
    def __update_state(self, control, changes, state):
        if len(changes) > 0:
            self.update_state_info(state)
        if len(state.stack) == 0 or state.stack[-1][0] < control.assignment.decision_level:
            state.stack.append((control.assignment.decision_level, len(state.lp_trail), len(state.cond_trail), len(state.oclit_trail), len(state.eq_trail)))
        state.recent_active = []
        state.lits_current += len(changes)
        for lit in changes:
            var=abs(lit)
            if lit in self.__lit_ta:
                state.lp_trail.append(lit)
                for cnum in self.__lit_ta[lit]:
                    state.active_cnum[cnum][1] = 1
                    rel = self.__constr[cnum][1][1]
                    if rel == '!=': 
                        self.__add_aux(control, state, cnum, lit) 
                    if state.active_cnum[cnum][0] == 0: 
                        state.recent_active.append(cnum)
            if not self.__nstrict and -lit in self.__lit_ta:
                if lit not in state.lp_trail:
                    state.lp_trail.append(lit)
                for cnum in self.__lit_ta[-lit]:
                    state.active_cnum[cnum][1] = -1
                    rel = self.__constr[cnum][1][1]
                    if rel == '=': 
                        self.__add_aux(control, state, cnum, lit) 
                    if state.active_cnum[cnum][0] == 0:
                        state.recent_active.append(cnum)
            if var in self.__clit_constr:
                state.cond_trail.append(lit)
                for cnum in self.__clit_constr[var]:
                    state.active_cnum[cnum][0] -= 1
                    if state.active_cnum[cnum][0] == 0 and state.active_cnum[cnum][1] != 0:
                        state.recent_active.append(cnum)
            if var in state.eqlit_inv: 
                state.eq_trail.append(lit)
                cnum = state.eqlit_inv[var]
                state.active_cnum[cnum][0] -= 1
                if state.active_cnum[cnum][0] == 0 and state.active_cnum[cnum][1] != 0:
                    state.recent_active.append(cnum) 
            if var in self.__obj_cond_lit:
                state.oclit_trail.append(lit)
                state.active_oclit -= 1 
                if state.active_oclit == 0:
                    state.oclit_recent_active = 1



    # adds an literal l to choose on l or -l for disjunktion of '!='
    def __add_aux(self, control, state, cnum, lit):
        if state.active_cnum[cnum][2] == 0:
            state.active_cnum[cnum][2] = 1
            nlit = control.add_literal()
            control.add_watch(nlit)
            control.add_watch(-nlit)
            state.eqlit[cnum] = nlit
            state.eqlit_inv[nlit] = cnum
            state.active_cnum[cnum][0] += 1
            control.add_clause([lit,nlit], lock=True) 
            state.total_lits += 1


    # returns false if lp system inconsistent else true
    def __check_consistency(self, control, state):
        if not state.lp.is_sat() and state.lits_current*100 / state.total_lits >= self.__core_confl_heur: 
            active_cnums = [cnum for cnum in state.active_cnum if state.active_cnum[cnum][0] == 0 and state.active_cnum[cnum][1] != 0]
            core_confl = self.__core_confl(state, [], active_cnums)
            clause = self.__get_confl(state, core_confl)
            if self.__trace:
                print('')
                print('core conflict constraints: ')
                for confl_cnum in core_confl:
                    print(state.clist[confl_cnum])
                print('')
            if not control.add_clause(clause) or not control.propagate():
                return False
            print('If this was printed, then I did something really wrong!') 
        if not state.lp.is_sat():
            active_cnums = [cnum for cnum in state.active_cnum if state.active_cnum[cnum][0] == 0 and state.active_cnum[cnum][1] != 0]
            clause = self.__get_confl(state, active_cnums)
            if self.__trace:
                print('')
                print('conflict constraints: ')
                for confl_cnum in active_cnums:
                    print(state.clist[confl_cnum])
                print('')
            if not control.add_clause(clause) or not control.propagate():
                return False
            print('If this was printed, then I did something really wrong!')
        return True



    # search core conflict
    def __core_confl(self, state, confl_cnums, active_cnums): 
        constr_list = [] 
        state.lp.reset()
        if confl_cnums != []:
            for cnum in confl_cnums:
                constr_list.append(state.clist[cnum]) 
            state.lp.add_constr(constr_list) 
            state.lp.solve_lp()
            if not state.lp.is_sat():
                return confl_cnums
        for i, cnum in enumerate(active_cnums):
            constr = state.clist[cnum]
            constr_list.append(constr)
            state.lp.add_constr([constr])
            state.lp.solve_lp()
            if not state.lp.is_sat():
                confl_cnums.append(cnum)
                tmp = confl_cnums[:]
                confl_cnums = self.__core_confl(state, tmp, active_cnums[:i])
                break
        return confl_cnums



    # generates conflict clause from a conflict 
    def __get_confl(self, state, confl_cnums):
        clause=[]
        for cnum in confl_cnums:
            lit = self.__constr[cnum][0]*state.active_cnum[cnum][1]
            clause.append(-1*lit)
            if state.active_cnum[cnum][2] == 1: 
                nlit = state.eqlit[cnum]
                if nlit in state.eq_trail:
                    clause.append(-nlit) 
                else:
                    clause.append(nlit)
            if cnum in self.__constr_clit:
                for clit in self.__constr_clit[cnum]:
                    if clit in state.cond_trail:
                        clause.append(-clit)
                    else:
                        clause.append(clit)
        clause = [x for x in clause if abs(x)>1]
        return clause

import clingo

def print_assignment(m):
    global prop
    prop.print_assignment(m.thread_id)


def get(val, default):
    return val if val != None else default


def main(prg):
    global prop
    prop = Propagator(prg.get_const("show"), prg.get_const("accuracy"), prg.get_const("nstrict"), prg.get_const("epsilon"), prg.get_const("solver"), prg.get_const("trace"), prg.get_const("core_confl"), prg.get_const("prop_heur"), prg.get_const("debug"), prg.get_const("ilp"))
    prg.register_propagator(prop)
    prg.ground([("base", [])])
    prg.solve(on_model = print_assignment)

#end.

#theory lp { 
    lin_term {
        - : 2, unary;
        * : 1, binary, left;
        + : 0, binary, left;
        - : 0, binary, left
    };
    bounds{
        - : 4, unary;
        * : 3, binary, left;
        / : 2, binary, left;
        + : 1, binary, left;
        - : 1, binary, left;   
        .. : 0, binary, left 
    };

    &lp/0   : lin_term, {<=,>=,>,<,=,!=}, bounds, any;
    &sum/0   : lin_term, {<=,>=,>,<,=,!=}, bounds, any;
    &objective/1 : lin_term, head;
    &minimize/0 : lin_term, head;
    &maximize/0 : lin_term, head;
    &dom/0 : bounds, {=}, lin_term, head
}.
