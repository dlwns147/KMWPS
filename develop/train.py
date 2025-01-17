from prerequisite import *
from model.transformer import *
from utils import *
from dataloader import *
from vocab import *


def build_model(config, voc1, voc2, device):
    """
        Args:
            config (dict): command line arguments
            voc1 (object of class Voc1): vocabulary of source
            voc2 (object of class Voc2): vocabulary of target
            device (torch.device): GPU device
        Returns:
            model (object of class TransformerModel): model
    """

    model = TransformerModel(config, voc1, voc2, device)
    model = model.to(device)

    return model


def train_model(model, train_dataloader, val_dataloader, voc1, voc2, device, config, epoch_offset=0,
                min_val_loss=float('inf'),
                max_val_bleu=0.0, max_val_acc=0.0, min_train_loss=float('inf'), max_train_acc=0.0, best_epoch=0):
    '''
        Args:
            model (object of class TransformerModel): model
            train_dataloader (object of class Dataloader): dataloader for train set
            val_dataloader (object of class Dataloader): dataloader for dev set
            voc1 (object of class Voc1): vocabulary of source
            voc2 (object of class Voc2): vocabulary of target
            device (torch.device): GPU device
            config (dict): command line arguments
            epoch_offset (int): How many epochs of training already done
            min_val_loss (float): minimum validation loss
            max_val_bleu (float): maximum valiadtion bleu score
            max_val_acc (float): maximum validation accuracy score
            min_train_loss (float): minimum train loss
            max_train_acc (float): maximum train accuracy
            best_epoch (int): epoch with highest validation accuracy
        Returns:
            max_val_acc (float): maximum validation accuracy score
    '''

    optimizer = get_optimizer(model, config)
    criterion = nn.CrossEntropyLoss()
    scheduler = get_scheduler(optimizer, config)

    estop_count = 0
    # epoch training
    for epoch in range(1, config.epochs + 1):
        od = OrderedDict()
        od['Epoch'] = epoch + epoch_offset

        batch_num = 1
        train_loss_epoch = 0.0
        train_acc_epoch = 0.0
        train_acc_epoch_cnt = 0.0
        train_acc_epoch_tot = 0.0
        max_trn_acc = 0
        val_loss_epoch = 0.0

        start_time = time()
        total_batches = len(train_dataloader)

        # trainloader
        for data in train_dataloader:
            ques = data['ques']

            sent1s = sents_to_idx(voc1, data['ques'], config.max_length, flag=0)
            sent2s = sents_to_idx(voc2, data['eqn'], config.max_length, flag=1)
            sent1_var, sent2_var, input_len1, input_len2 = process_batch(sent1s, sent2s, voc1, voc2, device)

            nums = data['nums']
            ans = data['ans']

            model.train()

            optimizer.zero_grad()
            output = model(ques, sent1_var, sent2_var[:-1, :])
            # output: (T-1) x BS x voc2.nwords [T-1 because it predicts after start symbol]
            output_dim = output.shape[-1]
            loss = criterion(output.reshape(-1, output_dim), sent2_var[1:, :].reshape(-1))

            loss.backward()
            if config.max_grad_norm > 0:  # prevent gradient exploding
                torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            train_loss_epoch += loss.item()

            #             if config.show_train_acc:
            #                 model.eval()

            #                 _, decoder_output = model.greedy_decode(ques, sent1_var, sent2_var, input_len2, validation=True)
            #                 temp_acc_cnt, temp_acc_tot, _ = cal_score(decoder_output, nums, ans)
            #                 train_acc_epoch_cnt += temp_acc_cnt
            #                 train_acc_epoch_tot += temp_acc_tot

            batch_num += 1
        # scheduler
        if scheduler is not None:
            scheduler.step()

        train_loss_epoch = train_loss_epoch / len(train_dataloader)
        #         if config.show_train_acc:
        #             train_acc_epoch = train_acc_epoch_cnt/train_acc_epoch_tot
        #         else:
        train_acc_epoch = 0.0

        time_taken = (time() - start_time) / 60.0

        # validation
        print('validation start')
        print('=' * 80)
        _, _, trn_acc_epoch = run_validation(config=config, model=model, val_dataloader=train_dataloader,
                                             voc1=voc1, voc2=voc2, device=device, epoch_num=epoch,
                                             vis_outputs=False)
        val_bleu_epoch, val_loss_epoch, val_acc_epoch = run_validation(config=config, model=model,
                                                                       val_dataloader=val_dataloader,
                                                                       voc1=voc1, voc2=voc2, device=device,
                                                                       epoch_num=epoch)

        if train_loss_epoch < min_train_loss:
            min_train_loss = train_loss_epoch

        if train_acc_epoch > max_train_acc:
            max_train_acc = train_acc_epoch

        #         if val_bleu_epoch[0] > max_val_bleu:
        #             max_val_bleu = val_bleu_epoch[0]

        if val_loss_epoch < min_val_loss:
            min_val_loss = val_loss_epoch

        if trn_acc_epoch > max_trn_acc:
            max_trn_acc = trn_acc_epoch

        if val_acc_epoch > max_val_acc:
            max_val_acc = val_acc_epoch

            best_epoch = epoch + epoch_offset
            state = {
                'state_dict': model.state_dict(),
                'voc1': model.voc1,
                'voc2': model.voc2,
            }

            #             logger.debug('Validation Bleu: {}'.format(val_bleu_epoch[0]))

            torch.save(state, f'./models/best_models_{epoch + epoch_offset}epoch_first_model.pth')
            estop_count = 0
        else:
            estop_count += 1

        #
        print('=' * 80)
        print(f'Epoch : {epoch + epoch_offset}')
        print('=' * 80)
        print(f'best_epoch : {best_epoch}')

        print(f'train_loss : {train_loss_epoch:.4f}')
        print(f'val_loss : {val_loss_epoch:.4f}')
        print(f'trn_acc_epoch : {trn_acc_epoch * 100:.2f}% ')
        print(f'val_acc_epoch : {val_acc_epoch * 100:.2f}%')

        print(f'min_train_loss : {min_train_loss:.4f}')
        print(f'min_val_loss : {min_val_loss:.4f}')
        print(f'max_trn_acc : {max_trn_acc * 100:.2f}%')
        print(f'max_val_acc : {max_val_acc * 100:.2f}%')
        #
        print('=' * 80)
        if estop_count > config.early_stopping:
            print('Early Stopping at Epoch: {} after no improvement in {} epochs'.format(epoch, estop_count))
            break

    return max_val_acc


def run_validation(config, model, val_dataloader, voc1, voc2, device, epoch_num, validation=True, vis_outputs=True):
    '''
        Args:
            config (dict): command line arguments
            model (object of class TransformerModel): model
            val_dataloader (object of class Dataloader): dataloader for dev set
            voc1 (object of class Voc1): vocabulary of source
            voc2 (object of class Voc2): vocabulary of target
            device (torch.device): GPU device
            epoch_num (int): Ongoing epoch number
            validation (bool): whether validating
        Returns:
            if config.mode == 'test':
                max_test_acc (float): maximum test accuracy obtained
            else:
                val_bleu_epoch (float): validation bleu score for this epoch
                val_loss_epoch (float): va;iadtion loss for this epoch
                val_acc (float): validation accuracy score for this epoch
    '''

    batch_num = 1
    val_loss_epoch = 0.0
    val_bleu_epoch = 0.0
    val_acc_epoch = 0.0
    val_acc_epoch_cnt = 0.0
    val_acc_epoch_tot = 0.0

    criterion = nn.CrossEntropyLoss()

    model.eval()  # Set specific layers such as dropout to evaluation mode

    refs = []
    hyps = []

    if config.mode == 'test':
        questions, gen_eqns, act_eqns, scores = [], [], [], []

    display_n = config.batch_size

    total_batches = len(val_dataloader)
    for data in val_dataloader:
        sent1s = sents_to_idx(voc1, data['ques'], config.max_length, flag=0)
        sent2s = sents_to_idx(voc2, data['eqn'], config.max_length, flag=0)
        nums = data['nums']
        names = data['names']
        ans = data['ans']
        ques = data['ques']

        sent1_var, sent2_var, input_len1, input_len2 = process_batch(sent1s, sent2s, voc1, voc2, device)

        val_loss, decoder_output = model.greedy_decode(ques, sent1_var, sent2_var, input_len2, criterion,
                                                       validation=True)

        # acc 측정
        temp_acc_cnt, temp_acc_tot, disp_corr = cal_score(decoder_output, nums, ans, names)
        val_acc_epoch_cnt += temp_acc_cnt
        val_acc_epoch_tot += temp_acc_tot
        ##########################################
        # decoder_output = sum(decoder_output, [])
        if vis_outputs:

            if config.val_outputs:
                for n in range(len(decoder_output)):
                    str_ = ''
                    for i in decoder_output[n]:
                        str_ += i

                    print(f'pred :{str_}')
                    print(f'true : {data["eqn"][n]}')
                    print(f'results : {disp_corr[n] == 1}')
                    print('')

        #             print(f'nums : {nums}')
        #             print(f'ans : {ans}')
        ##########################################

        #         sent1s = idx_to_sents(voc1, sent1_var, no_eos= True)
        #         sent2s = idx_to_sents(voc2, sent2_var, no_eos= True)

        #         refs += [[' '.join(sent2s[i])] for i in range(sent2_var.size(1))]
        #         hyps += [' '.join(decoder_output[i]) for i in range(sent1_var.size(1))]

        if config.mode == 'test':
            questions += data['ques']
            gen_eqns += [' '.join(decoder_output[i]) for i in range(sent1_var.size(1))]
            act_eqns += [' '.join(sent2s[i]) for i in range(sent2_var.size(1))]
            scores += [cal_score([decoder_output[i]], [nums[i]], [ans[i]], [data['eqn'][i]])[0] for i in
                       range(sent1_var.size(1))]

        val_loss_epoch += val_loss
        batch_num += 1

    val_bleu_epoch = 0  # bleu_scorer(refs, hyps)
    if config.mode == 'test':
        results_df = pd.DataFrame([questions, act_eqns, gen_eqns, scores]).transpose()
        results_df.columns = ['Question', 'Actual Equation', 'Generated Equation', 'Score']
        csv_file_path = os.path.join(config.outputs_path, config.dataset + '.csv')
        #         results_df.to_csv(csv_file_path, index = False)
        return sum(scores) / len(scores)

    val_acc_epoch = val_acc_epoch_cnt / val_acc_epoch_tot

    return val_bleu_epoch, val_loss_epoch / len(val_dataloader), val_acc_epoch