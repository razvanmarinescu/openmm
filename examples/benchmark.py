from __future__ import print_function
import openmm.app as app
import openmm as mm
import openmm.unit as unit
from datetime import datetime
import os
from argparse import ArgumentParser

def timeIntegration(context, steps, initialSteps):
    """Integrate a Context for a specified number of steps, then return how many seconds it took."""
    context.getIntegrator().step(initialSteps) # Make sure everything is fully initialized
    context.getState(getEnergy=True)
    start = datetime.now()
    context.getIntegrator().step(steps)
    context.getState(getEnergy=True)
    end = datetime.now()
    elapsed = end-start
    return elapsed.seconds + elapsed.microseconds*1e-6

def downloadAmberSuite():
    """Download and extract Amber benchmark to Amber20_Benchmark_Suite/ in current directory."""
    dirname = 'Amber20_Benchmark_Suite'
    url = 'https://ambermd.org/Amber20_Benchmark_Suite.tar.gz'
    if not os.path.exists(dirname):
        import urllib.request
        print('Downloading', url)
        filename, headers = urllib.request.urlretrieve(url, filename='Amber20_Benchmark_Suite.tar.gz')
        import tarfile
        print('Extracting', filename)
        tarfh = tarfile.open(filename, 'r:gz')
        tarfh.extractall(path=dirname)
    return dirname

def runOneTest(testName, options):
    """Perform a single benchmarking simulation."""
    explicit = (testName not in ('gbsa', 'amoebagk'))
    amoeba = (testName in ('amoebagk', 'amoebapme'))
    apoa1 = testName.startswith('apoa1')
    amber = (testName.startswith('amber'))
    hydrogenMass = None
    print()
    if amoeba:
        print('Test: %s (epsilon=%g)' % (testName, options.epsilon))
    elif testName == 'pme':
        print('Test: pme (cutoff=%g)' % options.cutoff)
    else:
        print('Test: %s' % testName)
    print('Ensemble: %s' % options.ensemble)
    platform = mm.Platform.getPlatformByName(options.platform)
    
    # Create the System.

    temperature = 300*unit.kelvin
    if explicit:
        friction = 1*(1/unit.picoseconds)
    else:
        friction = 91*(1/unit.picoseconds)
    if amoeba:
        constraints = None
        epsilon = float(options.epsilon)
        if explicit:
            ff = app.ForceField('amoeba2009.xml')
            pdb = app.PDBFile('5dfr_solv-cube_equil.pdb')
            cutoff = 0.7*unit.nanometers
            vdwCutoff = 0.9*unit.nanometers
            system = ff.createSystem(pdb.topology, nonbondedMethod=app.PME, nonbondedCutoff=cutoff, vdwCutoff=vdwCutoff, constraints=constraints, ewaldErrorTolerance=0.00075, mutualInducedTargetEpsilon=epsilon, polarization=options.polarization)
        else:
            ff = app.ForceField('amoeba2009.xml', 'amoeba2009_gk.xml')
            pdb = app.PDBFile('5dfr_minimized.pdb')
            system = ff.createSystem(pdb.topology, nonbondedMethod=app.NoCutoff, constraints=constraints, mutualInducedTargetEpsilon=epsilon, polarization=options.polarization)
        for f in system.getForces():
            if isinstance(f, mm.AmoebaMultipoleForce) or isinstance(f, mm.AmoebaVdwForce) or isinstance(f, mm.AmoebaGeneralizedKirkwoodForce) or isinstance(f, mm.AmoebaWcaDispersionForce):
                f.setForceGroup(1)
        dt = 0.002*unit.picoseconds
        if options.ensemble == 'NVE':
            integ = mm.MTSIntegrator(dt, [(0,2), (1,1)])
        else:
            integ = mm.MTSLangevinIntegrator(temperature, friction, dt, [(0,2), (1,1)])
        positions = pdb.positions
    elif amber:
        dirname = downloadAmberSuite()
        names = {'amber20-dhfr':'JAC',  'amber20-factorix':'FactorIX', 'amber20-cellulose':'Cellulose', 'amber20-stmv':'STMV'}
        fileName = names[testName]
        prmtop = app.AmberPrmtopFile(os.path.join(dirname, f'PME/Topologies/{fileName}.prmtop'))
        inpcrd = app.AmberInpcrdFile(os.path.join(dirname, f'PME/Coordinates/{fileName}.inpcrd'))
        positions = inpcrd.positions
        dt = 0.004*unit.picoseconds
        method = app.PME
        cutoff = options.cutoff
        constraints = app.HBonds
        hydrogenMass = 1.5*unit.amu
        system = prmtop.createSystem(nonbondedMethod=method, nonbondedCutoff=cutoff, constraints=constraints)
        if options.ensemble == 'NVE':
            integ = mm.VerletIntegrator(dt)
        else:
            integ = mm.LangevinMiddleIntegrator(temperature, friction, dt)
    else:
        if apoa1:
            ff = app.ForceField('amber14/protein.ff14SB.xml', 'amber14/lipid17.xml', 'amber14/tip3p.xml')
            pdb = app.PDBFile('apoa1.pdb')
            if testName == 'apoa1pme':
                method = app.PME
                cutoff = options.cutoff
            elif testName == 'apoa1ljpme':
                method = app.LJPME
                cutoff = options.cutoff
            else:
                method = app.CutoffPeriodic
                cutoff = 1*unit.nanometers
        elif explicit:
            ff = app.ForceField('amber99sb.xml', 'tip3p.xml')
            pdb = app.PDBFile('5dfr_solv-cube_equil.pdb')
            if testName == 'pme':
                method = app.PME
                cutoff = options.cutoff
            else:
                method = app.CutoffPeriodic
                cutoff = 1*unit.nanometers
        else:
            ff = app.ForceField('amber99sb.xml', 'amber99_obc.xml')
            pdb = app.PDBFile('5dfr_minimized.pdb')
            method = app.CutoffNonPeriodic
            cutoff = 2*unit.nanometers
        if options.heavy:
            dt = 0.005*unit.picoseconds
            constraints = app.AllBonds
            hydrogenMass = 4*unit.amu
            if options.ensemble == 'NVE':
                integ = mm.VerletIntegrator(dt)
            else:
                integ = mm.LangevinIntegrator(temperature, friction, dt)
        else:
            dt = 0.004*unit.picoseconds
            constraints = app.HBonds
            hydrogenMass = 1.5*unit.amu
            if options.ensemble == 'NVE':
                integ = mm.VerletIntegrator(dt)
            else:
                integ = mm.LangevinMiddleIntegrator(temperature, friction, dt)
        positions = pdb.positions
        system = ff.createSystem(pdb.topology, nonbondedMethod=method, nonbondedCutoff=cutoff, constraints=constraints, hydrogenMass=hydrogenMass)
    if options.ensemble == 'NPT':
        system.addForce(mm.MonteCarloBarostat(1*unit.bar, temperature, 100))
    print('Step Size: %g fs' % dt.value_in_unit(unit.femtoseconds))
    properties = {}
    initialSteps = 5
    if options.device is not None and platform.getName() in ('CUDA', 'OpenCL'):
        properties['DeviceIndex'] = options.device
        if ',' in options.device or ' ' in options.device:
            initialSteps = 250
    if options.precision is not None and platform.getName() in ('CUDA', 'OpenCL'):
        properties['Precision'] = options.precision

    # Run the simulation.
    
    integ.setConstraintTolerance(1e-5)
    if len(properties) > 0:
        context = mm.Context(system, integ, platform, properties)
    else:
        context = mm.Context(system, integ, platform)
    context.setPositions(positions)
    print('number of atoms', len(positions))
    if amber:
        if inpcrd.boxVectors is not None:
            context.setPeriodicBoxVectors(*inpcrd.boxVectors)
        mm.LocalEnergyMinimizer.minimize(context, 100*unit.kilojoules_per_mole/unit.nanometer)
    context.setVelocitiesToTemperature(temperature)

    steps = 20
    while True:
        time = timeIntegration(context, steps, initialSteps)
        if time >= 0.5*options.seconds:
            break
        if time < 0.5:
            steps = int(steps*1.0/time) # Integrate enough steps to get a reasonable estimate for how many we'll need.
        else:
            steps = int(steps*options.seconds/time)
    print('Integrated %d steps in %g seconds' % (steps, time))
    print('%g ns/day' % (dt*steps*86400/time).value_in_unit(unit.nanoseconds))

# Parse the command line options.

parser = ArgumentParser()
platformNames = [mm.Platform.getPlatform(i).getName() for i in range(mm.Platform.getNumPlatforms())]
parser.add_argument('--platform', dest='platform', choices=platformNames, help='name of the platform to benchmark')
parser.add_argument('--test', dest='test', choices=('gbsa', 'rf', 'pme', 'apoa1rf', 'apoa1pme', 'apoa1ljpme', 'amoebagk', 'amoebapme', 'amber20-dhfr',  'amber20-factorix', 'amber20-cellulose', 'amber20-stmv'), 
    help='the test to perform: gbsa, rf, pme, apoa1rf, apoa1pme, apoa1ljpme, amoebagk, amoebapme,  amber20-dhfr,  amber20-factorix, amber20-cellulose, amber20-stmv [default: all except amber-*]')
parser.add_argument('--ensemble', default='NVT', dest='ensemble', choices=('NPT', 'NVE', 'NVT'), help='the thermodynamic ensemble to simulate [default: NVT]')
parser.add_argument('--pme-cutoff', default=0.9, dest='cutoff', type=float, help='direct space cutoff for PME in nm [default: 0.9]')
parser.add_argument('--seconds', default=60, dest='seconds', type=float, help='target simulation length in seconds [default: 60]')
parser.add_argument('--polarization', default='mutual', dest='polarization', choices=('direct', 'extrapolated', 'mutual'), help='the polarization method for AMOEBA: direct, extrapolated, or mutual [default: mutual]')
parser.add_argument('--mutual-epsilon', default=1e-5, dest='epsilon', type=float, help='mutual induced epsilon for AMOEBA [default: 1e-5]')
parser.add_argument('--heavy-hydrogens', action='store_true', default=False, dest='heavy', help='repartition mass to allow a larger time step')
parser.add_argument('--device', default=None, dest='device', help='device index for CUDA or OpenCL')
parser.add_argument('--precision', default='single', dest='precision', choices=('single', 'mixed', 'double'), help='precision mode for CUDA or OpenCL: single, mixed, or double [default: single]')
args = parser.parse_args()
if args.platform is None:
    parser.error('No platform specified')
print('Platform:', args.platform)
if args.platform in ('CUDA', 'OpenCL'):
    print('Precision:', args.precision)
    if args.device is not None:
        print('Device:', args.device)

# Run the simulations.

if args.test is None:
    for test in ('gbsa', 'rf', 'pme', 'apoa1rf', 'apoa1pme', 'apoa1ljpme', 'amoebagk', 'amoebapme'):
        try:
            runOneTest(test, args)
        except Exception as ex:
            print('Test failed: %s' % ex.message)
else:
    runOneTest(args.test, args)
