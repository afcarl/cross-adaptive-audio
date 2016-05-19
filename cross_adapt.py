from __future__ import absolute_import
from __future__ import print_function
import template_handler
import csound_handler
import os
import settings
import sound_file
import MultiNEAT as NEAT
import standardizer
import copy
import experiment


class CrossAdapter(object):
    def __init__(self, input_sound, neural_input_vectors, effect, parameter_lpf_cutoff=20):
        self.input_sound = input_sound
        self.neural_input_vectors = neural_input_vectors
        self.effect = effect
        self.parameter_lpf_cutoff = parameter_lpf_cutoff

    def produce_output_sounds(self, individuals):
        processes = []
        csd_paths = []
        for that_individual in individuals:
            process, output_sound, csd_path = self.produce_output_sound(that_individual)
            processes.append(process)
            csd_paths.append(csd_path)
            that_individual.set_output_sound(output_sound)

        for i in range(len(processes)):
            processes[i].wait()
            try:
                os.remove(csd_paths[i])
            except OSError:
                print('Warning: Failed to remove {}'.format(csd_paths[i]))

    def produce_output_sound(self, that_individual):
        output_filename = '{0}.cross_adapted.{1}.wav'.format(
            self.input_sound.filename,
            that_individual.get_id()
        )

        # this creates a neural network (phenotype) from the genome
        net = NEAT.NeuralNetwork()
        that_individual.genotype.BuildPhenotype(net)

        output_vectors = []
        for input_vector in self.neural_input_vectors:
            net.Flush()
            net.Input(input_vector)
            net.Activate()
            output = net.Output()
            output = [min(1.0, max(0.0, x)) for x in output]
            output_vectors.append(output)

        that_individual.set_neural_output(zip(*output_vectors))

        process, resulting_sound, csd_path = self.cross_adapt(
            parameter_vectors=output_vectors,
            effect=self.effect,
            output_filename=output_filename
        )

        return process, resulting_sound, csd_path

    def cross_adapt(self, parameter_vectors, effect, output_filename):
        vectors = copy.deepcopy(parameter_vectors)

        # map normalized values to the appropriate ranges of the effect parameters
        for i in range(effect.num_parameters):
            mapping = effect.parameters[i]['mapping']
            min_value = mapping['min_value']
            max_value = mapping['max_value']
            skew_factor = mapping['skew_factor']

            for parameter_vector in vectors:
                parameter_vector[i] = standardizer.Standardizer.get_mapped_value(
                    normalized_value=parameter_vector[i],
                    min_value=min_value,
                    max_value=max_value,
                    skew_factor=skew_factor
                )

        channels = zip(*vectors)

        channels_csv = []
        for channel in channels:
            channel_csv = ','.join(map(str, channel))
            channels_csv.append(channel_csv)

        template = template_handler.TemplateHandler(self.effect.template_file_path)
        template.compile(
            input_sound_filename=self.input_sound.filename,
            parameter_channels=channels_csv,
            ksmps=settings.HOP_SIZE,
            duration=self.input_sound.get_duration(),
            parameter_lpf_cutoff=self.parameter_lpf_cutoff
        )

        csd_path = os.path.join(
            settings.CSD_DIRECTORY,
            experiment.Experiment.folder_name,
            output_filename + '.csd'
        )
        template.write_result(csd_path)
        csound = csound_handler.CsoundHandler(csd_path)
        process = csound.run(output_filename, async=True)
        output_sound_file = sound_file.SoundFile(
            output_filename,
            is_input=False
        )
        return process, output_sound_file, csd_path
